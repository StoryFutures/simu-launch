import asyncio
import base64
import datetime
import json
import multiprocessing
import subprocess
import os
import platform
import time
from collections import Counter
from functools import partial, wraps
from logging.handlers import RotatingFileHandler
from multiprocessing import Process, Pool, cpu_count

import cv2
import numpy as np
import logging
from fastapi import FastAPI, UploadFile, File, Form, Depends
from fastapi.encoders import jsonable_encoder
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.decorator import cache
from fastapi_utils.tasks import repeat_every
from ppadb import InstallError
from ppadb.client import Client as AdbClient
from ppadb.client_async import ClientAsync as AdbClientAsync
from ppadb.device import Device
from ppadb.device_async import DeviceAsync
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.background import BackgroundTasks
from starlette.requests import Request
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

logger = logging.getLogger()
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()

fh = RotatingFileHandler("api.log",mode="a",maxBytes = 100*1024, backupCount = 3)
formatter = logging.Formatter(
    "%(asctime)s - %(module)s - %(funcName)s - line:%(lineno)d - %(levelname)s - %(message)s"
)

ch.setFormatter(formatter)
fh.setFormatter(formatter)
logger.addHandler(ch) #Exporting logs to the screen
logger.addHandler(fh) #Exporting logs to a file

from adb_layer import adb_image
from helpers import (
    launch_app,
    save_file,
    process_devices,
    connect_actions,
    HOME_APP_APK,
    home_app_installed, HOME_APP_ENABLED, check_alive, wait_host_port,
)
from models_pydantic import Volume, Devices, Experience, NewExperience, StartExperience
from sql_app import models, crud
from sql_app.crud import (
    get_all_apk_details,
    get_apk_details,
    set_device_icon,
    get_device_decorations,
    crud_defaults,
)
from sql_app.database import engine, SessionLocal
from sql_app.schemas import APKDetailsCreate, APKDetailsBase

models.Base.metadata.create_all(bind=engine)

app = FastAPI()
location = "/home/simu-launch/" if "Linux" in platform.system().lower() else ""
app.mount("/static", StaticFiles(directory=location + "static"), name="static")
templates = Jinja2Templates(directory=location + "templates")

simu_application_name = ""
global_volume = 10

screenshots_enabled: int = 0
manual_screenshots_enabled: int = 0

icons = [
    "3-bars",
    "2-bars",
    "1-bar",
    "circle-fill",
    "square-fill",
    "plus-lg",
    "heart-fill",
    "triangle-fill",
]
cols = ["red", "pink", "fuchsia", "blue", "green"]

check_for_new_devices_poll_s = 8
defaults = {
    "screen_width": 192,
    "screen_height": 108,
    "check_for_new_devices_poll": check_for_new_devices_poll_s * 1000,
    "screenshots_enabled": screenshots_enabled,
    "manual_screenshots_enabled": manual_screenshots_enabled,
}
crud_defaults(SessionLocal(), defaults)

FastAPICache.init(InMemoryBackend())

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


BASE_PORT = 5555

client: AdbClient = AdbClient(host="127.0.0.1", port=5037)
client_async: AdbClientAsync = AdbClientAsync(host="127.0.0.1", port=5037)


def is_wireless(serial):
    return '.' in serial


def shell_command(device_id: str, command):
    outcome = subprocess.run([f"adb", '-s', f"{device_id } '{command}'"], stdout=subprocess.PIPE).stdout.decode('ascii')
    return outcome


@app.on_event("startup")
@repeat_every(seconds=30*1, raise_exceptions=True)
async def wake():
    logging.info(f'check screens awake {time.strftime("%H:%M:%S", time.localtime())}')

    my_devices = await scan_devices()
    my_devices = [device for device in my_devices if is_wireless(device.serial)]
    count = 0
    devices_count = len(my_devices)

    for device in my_devices:
        count += 1
        if not await check_alive(device, client):
            continue
        screen_state = subprocess.run([f"adb", '-s', device.serial, "shell", "dumpsys",
                                  "power", "|", 'grep', "\'Display Power: state=OFF\'"],
                                 stdout=subprocess.PIPE).stdout.decode('ascii')

        screen_state_off = len(screen_state) > 0
        if screen_state_off:
            logging.info(f'{count}/{devices_count} Waking screen on device {device.serial}')
            outcome = subprocess.run([f"adb", '-s', device.serial, "shell", "input", "keyevent", "26"],
                                     stdout=subprocess.PIPE).stdout.decode('ascii')
        else:
            logging.info(f'{count}/{devices_count} Screen already on with device {device.serial}')


async def scan_devices():
    outcome = subprocess.run(["adb", "devices"], stdout=subprocess.PIPE).stdout.decode('ascii')
    alive = [serial.split('\t')[0] for serial in outcome.splitlines()[1:] if 'offline' not in serial and serial]
    my_devices = [client.device(serial) for serial in alive]
    return my_devices

def check_adb_running(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            device: Device
            client.devices()

        except RuntimeError as e:
            err = e.__str__()
            if "no such device" in err:
                logging.info("issue disconnecting disconnected wifi device (caution)")
            elif e.__str__().find("Is adb running on your computer?"):
                logging.info("ADB Server not running, starting it now!")
                command = os.system("adb start-server")
                logging.info(command)
        return await func(*args, **kwargs)

    return wrapper


@app.post("/settings")
async def settings(screen_updates: int = Form(...), db: Session = Depends(get_db)):
    crud.update_settings(db, screen_updates=screen_updates)
    crud_defaults(SessionLocal(), defaults)
    return {"success": True}


@app.get("/devices")
@cache(expire=check_for_new_devices_poll_s)
async def devices(db: Session = Depends(get_db)):
    """
        Gets a list of all devices connected via ADB.

    :return: a dict object containing a list of devices and any errors.
    """

    _devices = []
    errs = []

    device: Device
    for device in await scan_devices():
        device_info = {
            "message": "",
            "id": "",
            "icon": "",
        }
        try:
            serial = str(device.serial)
            my_device_icon = get_device_decorations(db, serial)
            device_info["id"] = serial
            device_info["icon"] = my_device_icon
            device_info["ip"] = len(serial.split(".")) >= 2

        except RuntimeError as e:
            errs.append(str(e))
        try:
            if await check_alive(device, client):
                device.get_state()
            else:
                device_info["message"] = f"<small>Wifi issue! Please <button class='btn btn-outline-info' " \
                                         f"onclick='disconnectSingleDevice(\"{device.serial}\")'>click to remove" \
                                         f"</button> the device or try and fix the problem.</small>"
        except RuntimeError as e:
            if "unauthorized" in str(e):
                device_info["message"] = "Unauthorised"
            if "disconnected" in str(e):
                device_info["message"] = "Disconnected"

        _devices.append(device_info)

    return {"devices": _devices, "errs": errs}


@app.get("/d")
@check_adb_running
async def devices_page(request: Request):
    return templates.TemplateResponse(
        "pages/devices_page.html",
        {
            "request": request,
            "app_name": simu_application_name,
            "icons": icons,
            "cols": cols,
            "defaults": defaults,
        },
    )


@app.get("/")
@check_adb_running
async def home(request: Request):
    """
        View mainly responsible for handling the front end, since nothing will happen on the backend at this endpoint.
    :param db: the database dependency
    :param request: the Request object
    :return: a TemplateResponse object containing the homepage
    """

    global simu_application_name

    return templates.TemplateResponse(
        "home-basic.html",
        {
            "request": request,
            "app_name": simu_application_name,
            "icons": icons,
            "cols": cols,
            "defaults": defaults,
        },
    )


@app.get("/monitor")
@check_adb_running
async def home(request: Request):
    """
        View mainly responsible for handling the front end, since nothing will happen on the backend at this endpoint.
    :param db: the database dependency
    :param request: the Request object
    :return: a TemplateResponse object containing the homepage
    """

    global simu_application_name

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "app_name": simu_application_name,
            "icons": icons,
            "cols": cols,
            "defaults": defaults,
        },
    )


@app.get("/experiences")
async def experiences(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        "experiences/set_experience_content.html",
        {
            "request": request,
            "choices": [item.apk_name for item in get_all_apk_details(db)],
        },
    )


@app.post("/start")
async def start(payload: StartExperience, db: Session = Depends(get_db)):
    """
        Starts the experience on all devices through the adb shell commands.

    :param payload: a list of devices which the experience will start on and the experience
    :param db: the database dependency
    :return: dictionary of all device serial numbers
    """
    client_list = process_devices(client, payload)

    global simu_application_name

    if payload.experience:
        simu_application_name = payload.experience
    else:
        return {"success": False, "error": "No experience specified!"}

    item = jsonable_encoder(crud.get_apk_details(db, apk_name=simu_application_name))

    try:
        if item is None:
            return {
                "success": False,
                "error": "Could not start experience. Are you sure you selected one?",
            }

        logging.info(
            "Starting experience "
            + simu_application_name
            + " on "
            + str(len(client_list))
            + " devices"
        )

        pool = Pool(cpu_count())
        launch_func = partial(
            launch_app,
            app_name=item["apk_name"],
            d_type=item["device_type"],
            command=item["command"],
        )
        pool.map(launch_func, client_list)
        pool.close()
        pool.join()
    except RuntimeError as e:
        return {"success": False, "error": e.__str__()}

    return {"success": True, "device_count": len(client_list)}


@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    command: str = Form(...),
    db: Session = Depends(get_db),
):
    """
        Upload an experience to the backend so that it can be later loaded on the device.
        It also creates a new database object with the experience.

    :param file: an UploadFile object containing the .apk file
    :param command: a Form object containing a string for the command to launch the experience
    :param db: the database dependency
    :return: a success dictionary signifying the operation was successful
    """

    try:
        contents = await file.read()
        save_file(file.filename, contents)

        global simu_application_name
        simu_application_name = file.filename

        device_type = 0 if command == "android" else 1

        item = APKDetailsBase(
            apk_name=file.filename,
            command="" if command == "android" else command,
            device_type=device_type,
        )

        crud.create_apk_details_item(
            db=db, item=APKDetailsCreate.parse_obj(item.dict())
        )

        return {"success": True}
    except IOError as e:
        return {"success": False, "error": e.__str__()}


@app.post("/load")
async def load(payload: Experience):
    """
        Installs the experience on selected or all devices.

    :param payload: the choice of experience specified by the user
    :return: a success dictionary signifying the operation was successful
    """

    client_list = process_devices(client, payload)

    apk_paths = os.listdir("apks")
    apk_path = "apks/"

    global simu_application_name
    simu_application_name = payload.experience

    if payload.experience in apk_paths:
        apk_path += payload.experience
    else:
        return {
            "success": False,
            "error": "Cannot find the Experience APK in the directory. Make sure you uploaded it!",
        }
    errs = []
    try:
        for device in client_list:
            if not await check_alive(device, client):
                errs.append(f'Problem installing on this device: {device.serial}. Temporarily unavailable')
                continue
            logging.info("Installing " + apk_path + " on " + device.serial)
            p = Process(target=device.install, args=(apk_path,))
            p.start()
    except InstallError as e:
        return {"success": False, "error": e.__str__()}

    if errs:
        return {"success": False, "error": ','.join(errs)}
    return {"success": True, "device_count": len(client_list)}


@app.post("/remove-remote-experience")
async def remove_remote_experience(payload: Experience, db: Session = Depends(get_db)):
    """
        Removes an experience from the database.

    :param payload: an Experience object containing the experience name.
    :param db: the database dependency
    :return: a success dictionary signifying the operation was successful
    """

    try:
        if payload.experience:
            db.delete(get_apk_details(db, apk_name=payload.experience))
            db.commit()
            return {"success": True}

        return {"success": False}
    except SQLAlchemyError as e:
        return {"success": False, "error": e.__str__()}


@app.post("/add-remote-experience")
async def add_remote_experience(payload: NewExperience, db: Session = Depends(get_db)):
    """
        Adds a new experience, which has either been previously installed or is available on the device already.

    :param payload: a NewExperience object containing all necessary details for creating a new experience
    :param db: the database dependency
    :return: a success dictionary signifying the operation was successful
    """

    try:
        device_type = 0 if payload.command == "android" else 1

        if payload.apk_name is None or payload.apk_name == "":
            raise SQLAlchemyError(
                "No APK name provided. Please make sure an APK name has been provided!"
            )

        item = APKDetailsBase(
            experience_name=payload.experience_name,
            apk_name=payload.apk_name,
            command="" if payload.command == "android" else payload.command,
            device_type=device_type,
        )

        crud.create_apk_details_item(
            db=db, item=APKDetailsCreate.parse_obj(item.dict())
        )

        logging.info("Remote experience added!")

        return {"success": True}
    except SQLAlchemyError as e:
        return {"success": False, "error": e.__str__()}


def launch_home_app(device_id: str):
    if HOME_APP_ENABLED:
        device = client.device(device_id)
        outcome = launch_app(
            device,
            app_name=HOME_APP_APK,
            d_type=True,
            command="com.unity3d.player.UnityPlayerActivity",
        )
        return outcome


@app.post("/stop")
async def stop(payload: Experience, db: Session = Depends(get_db)):
    """
        Stops the experience on all devices through ADB shell commands

    :param payload: an Experience object containing a list of devices and the experience to stop
    :param db: the database dependency
    :return: a dictionary containing the success flag of the operation and any errors
    """

    client_list = process_devices(client, payload)

    if not payload.experience:
        return {"success": False, "error": "No experience to be stopped"}

    item = jsonable_encoder(crud.get_apk_details(db, apk_name=payload.experience))

    if item is None:
        return {
            "success": False,
            "error": "No application to stop, make sure there is one running!",
        }

    app_name = (
        item["apk_name"] if ".apk" not in item["apk_name"] else item["apk_name"][:-4]
    )

    try:
        for device in client_list:
            logging.info("Stopped experience on device " + device.serial)
            command = "am force-stop " + app_name
            if await check_alive(device, client):
                device.shell(command)
                launch_home_app(device.serial)
    except RuntimeError as e:
        return {"success": False, "error": e.__str__()}

    return {"success": True, "stopped_app": app_name}


@app.post("/connect")
@app.get("/connect")
async def connect_raw(request: Request):
    """
        Connects a device wirelessly to the server on port 5555. After the device is connected, it can be unplugged from
        the USB.

    :param request: The Request parameter which is used to receive the device data.
    :return: a dictionary containing the success flag of the operation and any errors
    """

    global BASE_PORT

    json = await request.json() if len((await request.body()).decode()) > 0 else {}

    remote_address = json["remote_address"] if "remote_address" in json else ""

    logging.info("json ", json)
    logging.info("address ", remote_address)

    if not remote_address:
        device_ip = request.client.host
    else:
        device_ip = remote_address

    try:
        if not remote_address:
            os.system("adb -s" + device_ip + " tcpip " + str(BASE_PORT))

        p = multiprocessing.Process(
            target=client.remote_connect, args=(device_ip, BASE_PORT)
        )
        p.start()

        p.join(5)

        if not p.is_alive():
            connected_device = Device(client, device_ip)
            connect_actions(
                connected_device,
                global_volume,
            )

            logging.info(
                "Established connection with client " + device_ip + ":" + str(BASE_PORT)
            )

            return {"success": True, "serial": device_ip}

        raise RuntimeError(
            "Could not connect device. Make sure the device is connected on the same router as the server!"
        )
    except RuntimeError as e:
        return {"success": False, "error": e.__str__()}


@app.get("/connect/{device_serial}")
async def connect(
    request: Request, device_serial: str, background_tasks: BackgroundTasks
):
    """
        Connects a device wirelessly to the server on port 5555. After the device is connected, it can be unplugged from
        the USB.

    :param background_tasks:
    :param device_serial:
    :param request: The Request parameter which is used to receive the device data.
    :return: a dictionary containing the success flag of the operation and any errors
    """
    global BASE_PORT

    json = await request.json() if len((await request.body()).decode()) > 0 else {}

    remote_address = ""

    device: Device = client.device(device_serial)

    logging.info("json ", json)
    logging.info("address ", remote_address)
    logging.info("device ", device_serial, device)

    if not remote_address:
        try:
            device_ip = device.shell("ip addr show wlan0")
        except RuntimeError:
            return {
                "success": False,
                "error": "Via a popup box within the headset you have not specified that this "
                "device can have permission to access the headset. You may need to enable 'USB connect dialogue' via"
                         "developer options in settings.",
            }
        device_ip = device_ip[device_ip.find("inet ") :]
        device_ip = device_ip[: device_ip.find("/")]
        device_ip = device_ip[device_ip.find(" ") + 1 :]
    else:
        device_ip = remote_address

    try:
        if not remote_address:
            os.system("adb -s" + device.serial + " tcpip " + str(BASE_PORT))

        p = multiprocessing.Process(
            target=client.remote_connect, args=(device_ip, BASE_PORT)
        )
        p.start()

        p.join(5)

        if not p.is_alive():
            cmd = "adb -s " + device.serial + " tcpip " + str(BASE_PORT)
            os.system(cmd)

        p = multiprocessing.Process(
            target=client.remote_connect, args=(device_ip, BASE_PORT)
        )
        p.start()

        p.join(5)

        if not p.is_alive():
            connected_device = Device(client, device_ip)

            background_tasks.add_task(
                connect_actions,
                connected_device,
                global_volume,
            )
            connected = await wait_host_port(device_ip, BASE_PORT, duration=5, delay=2)

            if connected:
                logging.info(
                    "Established connection with client "
                    + device_ip
                    + ":"
                    + str(BASE_PORT)
                )
                message = f"successfully added device {device_ip}."
                if HOME_APP_ENABLED:
                    if not home_app_installed(device):
                        message += (
                            f" Please note that the home app needed to be installed, so your device wont "
                            f"appear for a few moments"
                        )
                return {"success": True, "serial": device_ip, "message": message}
            else:
                return {
                    "success": False,
                    "error": "Your device is on a different wifi network",
                }

        raise RuntimeError(
            "Could not connect device. Make sure the device is connected on the same router as the server!"
        )
    except RuntimeError as e:
        return {"success": False, "error": e.__str__()}


@app.post("/disconnect")
async def disconnect(payload: Devices):
    """
        Disconnects devices from the server.

    :devices: a list of devices to disconnect from
    :return: a dictionary containing the success flag of the operation and any errors
    """

    global BASE_PORT

    client_list = process_devices(client, payload)

    try:
        device: Device
        for device in client_list:
            logging.info("Disconnecting device " + device.serial + " from server!")
            working = client.remote_disconnect(device.serial)
            if not working:
                return {
                    "success": False,
                    "error": "Encountered an error disconnecting device with ID/IP: "
                    + device.serial,
                }

        return {"success": True}
    except RuntimeError as e:
        return {"success": False, "error_log": e.__str__()}


@app.post("/restart")
async def restart(payload: Devices):
    """
        Restarts devices

    :devices: a list of devices to restart
    :return: a dictionary containing the success flag of the operation and any errors
    """

    global BASE_PORT

    client_list = process_devices(client, payload)

    try:
        device: Device
        for device in client_list:
            logging.info("Restarting device " + device.serial + " from server!")
            working = device.reboot()
            if not working:
                return {
                    "success": False,
                    "error": "Encountered an error restarting device with ID/IP: "
                    + device.serial,
                }

        return {"success": True}
    except RuntimeError as e:
        return {"success": False, "error_log": e.__str__()}


@app.post("/exit-server")
async def exit_server():
    """
        Kills the ADB server and all connections with devices. Essentially a system shutdown, where the FastAPI backend
        remains alive.

    :return: a dictionary containing the success flag
    """

    try:
        result = client.kill()
    except RuntimeError as e:
        return {"success": False, "errors": e.__str__()}

    return {"success": result}


@app.get("/screen-grab")
async def screen_grab():
    """
        Gets a screenshot from every device.
    :param request: the Request object
    :return: a dictionary containing the success flag
    """

    my_devices = await scan_devices()

    screen_caps_folder = "screenshots/"

    try:
        folder = (
            screen_caps_folder + datetime.datetime.now().strftime("%m%d%Y%H%M%S") + "/"
        )
        os.makedirs(folder)
        i = 0
        for device in my_devices:
            if await check_alive(device, client):
                result = device.screencap()
                with open(folder + "screen" + str(i) + ".png", "wb") as fp:
                    fp.write(result)
                i += 1
    except RuntimeError as e:
        return {"success": False, "errors": e.__str__()}

    return {"success": True}


@app.post("/volume")
async def volume(payload: Volume):
    """
        Sets the volume of a list of devices.

    :param volume: a Volume object containing a list of devices and a volume
    :return: a dictionary containing the success flag
    """

    client_list = process_devices(client, payload)

    global global_volume
    global_volume = payload.volume

    fails = []
    for device in client_list:
        if await check_alive(device, client):
            try:
                device.shell(f"cmd media_session volume --stream 3 --set {payload.volume}")
                device.shell(f"media volume --stream 3 --set {payload.volume}")
            except RuntimeError as e:
                fails.append(e)

    if fails:
        return {"success": False, "fails": str(fails)}

    return {"success": True}


devices_info = {}


async def check_image(device_serial, refresh_ms, size):
    if await check_alive(client.device(device_serial), client):
        pass
    img = adb_image(device_serial)

    if img and len(img) > 5 and img[5] == 0x0d:
        img = img.replace(b'\r\n', b'\n')


    _image = None
    try:
        _image = cv2.imdecode(np.frombuffer(img, np.uint8), cv2.IMREAD_COLOR)
    except cv2.error:
        return None

    if _image is None:
        return None

    _image = _image[0: _image.shape[0], 0 : int(_image.shape[1] * 0.5)]

    height = _image.shape[0]
    width = int(_image.shape[1] / height * defaults["screen_height"])
    height = defaults["screen_height"]

    dsize = (width, height)
    image = cv2.resize(_image, dsize)

    _, encoded_img = cv2.imencode(".png", image)
    return base64.b64encode(encoded_img).decode("utf-8")


@app.get("/device-screen/{refresh_ms}/{size}/{device_serial}")
async def devicescreen(
    request: Request, refresh_ms: int, size: str, device_serial: str
):
    try:
        image = await check_image(device_serial, refresh_ms, size)
        if not image:
            return {"success": False}
        return {"base64_image": image}
    except RuntimeError as e:
        if "device offline" in str(e):
            return {"success": False, "device-offline": device_serial}

    return {"success": False}


@app.get("/battery/{device_serial}")
async def battery(device_serial: str):
    try:
        device: Device = client.device(device_serial)
        if not device:
            return "Device does not exist"
        battery_level = device.get_battery_level()
        if str(battery_level) == "null":
            return "?"
        return battery_level
    except RuntimeError as e:
        if "device offline" in str(e):
            return 0
    return 0


async def _experiences(device_serial: str = None, device: Device = None) -> []:
    if device is None:
        device: Device = client.device(device_serial)

    payload = device.shell("cmd package list packages -3").strip()

    experiences = []

    for package in payload.split("\n"):
        package = package.replace("package:", "")
        experiences.append({"package": package, "name": package})

    experiences.sort(key=lambda el: el["name"])

    return experiences

@app.get("/loaded-experiences/{device_serial}")
async def loaded_experiences(request: Request, device_serial: str):
    device: Device = client.device(device_serial)
    # https://stackoverflow.com/a/53634311/960471

    return await _experiences(device_serial)


@app.get("/device-experiences/{device_serial}")
async def device_experiences(request: Request, device_serial: str):
    device: Device = client.device(device_serial)
    # https://stackoverflow.com/a/53634311/960471

    return templates.TemplateResponse(
        "experiences/device_experiences.html",
        {
            "request": request,
            "device": device_serial,
            "experiences": await _experiences(device_serial),
        },
    )


@app.get("/devices-experiences")
async def devices_experiences(request: Request):
    # https://stackoverflow.com/a/53634311/960471

    devices_lookup = {}
    counter = Counter()

    for device in await scan_devices():
        experiences = await _experiences(device=device)

        experiences_map = {el["package"]: el["name"] for el in experiences}
        counter.update(experiences_map.keys())
        devices_lookup[device.serial] = experiences_map

    combined = {}
    for experience in [key for key, val in counter.most_common()]:
        row = []
        for device_id, experience_map in devices_lookup.items():
            if experience in experience_map:
                row.append(device_id)
            else:
                row.append("")
        combined[experience] = row

    return templates.TemplateResponse(
        "experiences/devices_experiences.html",
        {
            "request": request,
            "combined": combined,
        },
    )


@app.get("/device-experiences/{device_serial}")
async def device_experiences(request: Request, device_serial: str):
    device: Device = client.device(device_serial)
    # https://stackoverflow.com/a/53634311/960471

    return templates.TemplateResponse(
        "experiences/device_experiences.html",
        {
            "request": request,
            "device": device_serial,
            "experiences": await _experiences(device_serial),
        },
    )


async def get_running_app(device: DeviceAsync):
    current_app = await device.shell(
        "dumpsys activity activities | grep ResumedActivity"
    )
    current_app = current_app.split(" ")[-2]
    return current_app.split("/")[0]


@app.post("/command/{command}/{device_serial}")
async def device_command(
    request: Request, command: str, device_serial: str, db: Session = Depends(get_db)
):
    device = None
    if device_serial != "ALL":
        device = await client_async.device(device_serial)
        if not await check_alive(device, client):
            return {"success": False, "message": "Connected problem with the device"}

    my_json = await request.json()
    experience = my_json["experience"]

    async def get_exp_info(_d: Device):
        my_info: str = await _d.shell(
            f"dumpsys package | grep {experience} | grep Activity"
        )
        my_info = my_info.strip().split("\n")[0]
        if not my_info:
            return ""
        return my_info.split(" ")[1]

    if command == "start":
        # https://stackoverflow.com/a/64241561/960471
        info = await get_exp_info(device)
        outcome = await device.shell(f"am start -n {info}")
        return {"success": "Starting" in outcome, "message": outcome}

    elif command == "stop":
        # https://stackoverflow.com/a/56078766/960471
        await device.shell(f"am force-stop {experience}")
        launch_home_app(device.serial)
        return {"success": True}
    elif command == "copy-details":
        info: str = await device.shell(
            f"dumpsys package | grep {experience} | grep Activity"
        )
        info = info.strip().split("\n")[0]
        info = info.split(" ")[1]
        item = APKDetailsBase(
            apk_name=info,
            device_type=2,
            command="",
        )

        crud.create_apk_details_item(
            db=db, item=APKDetailsCreate.parse_obj(item.dict())
        )
        return {"success": True}

    elif command == "stop-some-experience":
        current_app = await get_running_app(device)
        if current_app == "com.oculus.shellenv":
            return {"success": True, "outcome": "No app to stop!"}
        outcome = await device.shell(f"am force-stop {current_app}")
        return {"success": True, "outcome": "Successfully stopped!"}

    ########### devices experiences menu
    elif command == "devices_experiences__stop_experience_some":
        my_devices = json.loads(my_json["devices"].replace("'", '"'))

        outcome = ""
        for device_serial in my_devices:
            device: DeviceAsync = await client_async.device(device_serial)
            if await check_alive(device, client):
                outcome = await device.shell(f"am force-stop {experience}")
                launch_home_app(device.serial)
            else:
                outcome = 'device(s) has a wifi connection issue'
        return {"success": True, "message": outcome}

    elif command == "devices_experiences__start_experience_some":
        my_devices = (
            my_json["devices"]
            .replace("[", "")
            .replace("]", "")
            .replace("'", "")
            .replace(" ", "")
        )
        devices_list = [x for x in my_devices.split(",") if len(x) > 0]

        info = await get_exp_info(await client_async.device(devices_list[0]))
        errs = []
        for device in devices_list:
            device: DeviceAsync = await client_async.device(device)
            if await check_alive(device, client):
                outcome = await device.shell(f"am start -n {info}")

                if "Exception" in outcome:
                    errs.append(f"An error occurred at device {device.serial}: \n" + outcome)
            else:
                errs.append('a device has a wifi connection issue')
        if errs:
            return {
                "success": False,
                "error": "Couldn't start experience on device. Make sure boundaries set up. "
                + " ".join(errs),
            }

        return {"success": True}

    ########### devices experiences menu

    return {"success": True, "outcome": "Unknown command:" + command}


@app.post("/set-device-icon/{device_serial}")
async def device_icon(
    request: Request, device_serial: str, db: Session = Depends(get_db)
):
    json = await request.json()
    col = json["col"]
    icon = json["icon"]
    text = json["text"]
    set_device_icon(db=db, device_id=device_serial, icon=icon, col=col, text=text)
    return {"success": True}


@app.get("/current-experience/{device_serial}")
async def current_experience(request: Request, device_serial: str):
    device = await client_async.device(device_serial)
    if not await check_alive(device, client):
        return {'current_app': 'DISCONNECTED'}
    current_app = await get_running_app(device)
    return {"current_app": current_app}
