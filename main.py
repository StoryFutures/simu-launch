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
from multiprocessing import Process, Pool, cpu_count

import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, Depends
from fastapi.encoders import jsonable_encoder
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.decorator import cache
from fastapi_utils.tasks import repeat_every
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.background import BackgroundTasks
from starlette.requests import Request, ClientDisconnect
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from adb_layer import scan_devices, scan_devices_and_state, adb_command, adb_image, adb_command_no_wait
from helpers import (
    launch_app,
    save_file,
    process_devices,
    connect_actions,
    HOME_APP_APK,
    home_app_installed, HOME_APP_ENABLED, install,
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
cols = ["red", "orange", "yellow", "blue", "green"]

check_for_new_devices_poll_s = 8

defaults = {
    "screen_width": 192,
    "screen_height": 108,
    "check_for_new_devices_poll": check_for_new_devices_poll_s * 1000,
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


async def wait_host_port(host, port, duration=10, delay=2):
    """Repeatedly try if a port on a host is open until duration seconds passed

    Parameters
    ----------
    host : str
        host ip address or hostname
    port : int
        port number
    duration : int, optional
        Total duration in seconds to wait, by default 10
    delay : int, optional
        delay in seconds between each try, by default 2

    Returns
    -------
    awaitable bool
    """
    tmax = time.time() + duration
    while time.time() < tmax:
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=5
            )
            writer.close()
            await writer.wait_closed()
            return True
        except:
            if delay:
                await asyncio.sleep(delay)
    return False

def is_wireless(serial):
    return '.' in serial

def shell_command(device_id: str, command):
    outcome = subprocess.run([f"adb", '-s', f"{device_id } '{command}'"], stdout=subprocess.PIPE).stdout.decode('ascii')
    return outcome


@app.on_event("startup")
@repeat_every(seconds=30*1, raise_exceptions=True)
async def wake():
    print(f'check screens awake {time.strftime("%H:%M:%S", time.localtime())}')

    my_devices = scan_devices_and_state()
    my_devices = [device for device, state in my_devices if is_wireless(device) and state == 'device']

    count = 0
    devices_count = len(my_devices)
    for device in my_devices:
        count += 1
        screen_state = subprocess.run([f"adb", '-s', device, "shell", "dumpsys",
                                  "power", "|", 'grep', "\'Display Power: state=OFF\'"],
                                 stdout=subprocess.PIPE).stdout.decode('ascii')

        screen_state_off = len(screen_state) > 0
        if screen_state_off:
            print(f'{count}/{devices_count} Waking screen on device {device}')
            adb_command_no_wait([f"adb", '-s', device, "shell", "input", "keyevent", "26"])
        else:
            print(f'{count}/{devices_count} Screen already on with device {device}')



async def check_alive(device_serial):
    if "." not in device_serial:
        return True
    try:
        ip_port = device_serial.split(":")
        ip = ip_port[0]
        port = int(ip_port[1])
        is_open = await wait_host_port(host=ip, port=port, duration=2, delay=1)

        if is_open:
            return True

    except RuntimeError as e:
        err = e.__str__()
        print("issue disconnecting disconnected wifi device (caution): " + err)

    return False

def check_adb_running(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        print('checking adb running')
        adb_command(['adb', 'devices'])
        print('checked adb running')
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

    for serial, state in scan_devices_and_state():
        if "offline" in state:
            continue

        device_info = {
            "message": "",
            "id": "",
            "icon": "",
        }
        try:
            my_device_icon = get_device_decorations(db, serial)
            device_info["id"] = serial
            device_info["icon"] = my_device_icon
            device_info["ip"] = len(serial.split(".")) >= 2

        except RuntimeError as e:
            errs.append(str(e))

        if "unauthorized" in state:
            device_info["message"] = "Unauthorised"
        elif "disconnected" in state:
            device_info["message"] = "Disconnected"
        elif "offline" in state:
            device_info["message"] = "Offline"

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
    client_list = process_devices(payload)

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

        print(
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

    client_list = process_devices(payload)

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

    for device_serial in client_list:
        if not await check_alive(device_serial):
            errs.append(f'Problem installing on this device: {device_serial}. Temporarily unavailable')
            continue
        print("Installing " + apk_path + " on " + device_serial)
        p = Process(target=install, args=(device_serial, apk_path,))
        p.start()

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

        print("Remote experience added!")

        return {"success": True}
    except SQLAlchemyError as e:
        return {"success": False, "error": e.__str__()}


def launch_home_app(device_id: str):
    if HOME_APP_ENABLED:
        outcome = launch_app(
            device_id,
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

    client_list = process_devices(payload)

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
        for device_serial in client_list:
            print("Stopped experience on device " + device_serial)
            command = "am force-stop " + app_name
            adb_command(command.split(' '))
            launch_home_app(device_serial)
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

    print("json ", json)
    print("address ", remote_address)

    if not remote_address:
        device_ip = request.client.host
    else:
        device_ip = remote_address

    try:
        if not remote_address:
            os.system("adb -s" + device_ip + " tcpip " + str(BASE_PORT))



        p = multiprocessing.Process(
            target=adb_command, args=(['connect', f"{device_ip}:{BASE_PORT}"], )
        )
        p.start()

        p.join(5)

        if not p.is_alive():
            connect_actions(
                device_ip,
                global_volume,
            )

            print(
                "Established connection with client " + device_ip + ":" + str(BASE_PORT)
            )

            return {"success": True, "serial": device_ip}

        print("alive")
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

    try:
        device_ip = adb_command(f"adb -s {device_serial} shell ip addr show wlan0 | grep inet".split(' '))
        device_ip = device_ip[device_ip.find("inet "):]
        device_ip = device_ip[: device_ip.find("/")]
        device_ip = device_ip[device_ip.find(" ") + 1:]

    except RuntimeError:
        return {
            "success": False,
            "error": "Via a popup box within the headset you have not specified that this "
            "device can have permission to access the headset.",
        }

    outcome = adb_command(f"adb -s {device_serial} tcpip {BASE_PORT}".split(' '))

    try:

        outcome = adb_command(f'adb connect {device_ip}'.split(' '))

        connected = await wait_host_port(device_ip, BASE_PORT, duration=5, delay=2)

        if connected:

            background_tasks.add_task(
                connect_actions,
                device_ip,
                global_volume,
            )

            print(
                "Established connection with client "
                + device_ip
                + ":"
                + str(BASE_PORT)
            )
            message = f"successfully added device {device_ip}."
            if HOME_APP_ENABLED:
                if not home_app_installed(device_ip):
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

    client_list = process_devices(payload)

    try:
        for device_serial in client_list:
            print("Disconnecting device " + device_serial + " from server!")
            working = adb_command(f'adb disconnect {device_serial}:{BASE_PORT}'.split(' '))
            if not working:
                return {
                    "success": False,
                    "error": "Encountered an error disconnecting device with ID/IP: "
                    + device_serial,
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

    client_list = process_devices(payload)

    try:
        for device_serial in client_list:
            print("Restarting device " + device_serial + " from server!")
            working = adb_command(f'adb -s {device_serial} shell reboot'.split(' '))
            if not working:
                return {
                    "success": False,
                    "error": "Encountered an error restarting device with ID/IP: "
                    + device_serial,
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
        result = adb_command(['kill-server',])
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

    my_devices = scan_devices()

    screen_caps_folder = "screenshots/"

    try:
        folder = (
            screen_caps_folder + datetime.datetime.now().strftime("%m%d%Y%H%M%S") + "/"
        )
        os.makedirs(folder)
        i = 0
        for device in my_devices:
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

    client_list = process_devices(payload)

    global global_volume
    global_volume = payload.volume

    fails = []
    for device in client_list:
        try:
            adb_command_no_wait(f"adb -s {device} shell cmd media_session volume --stream 3 --set {payload.volume}".split(' '))
            adb_command_no_wait(f"adb -s {device} shell media volume --stream 3 --set {payload.volume}".split(' '))
        except RuntimeError as e:
            fails.append(e)

    if fails:
        return {"success": False, "fails": str(fails)}

    return {"success": True}


devices_info = {}


async def check_image(device_serial, refresh_ms, size):

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



@cache(expire=1)
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
    battery_level = adb_command(f'adb -s {device_serial} shell dumpsys battery | grep level'.split(' '))
    if str(battery_level) == "null":
        return "?"
    return battery_level.replace('level: ', '')




async def _experiences(device_serial: str = None) -> []:

    payload = adb_command(f"adb -s {device_serial} shell cmd package list packages -3".split(' ')).strip()

    experiences = []

    for package in payload.split("\n"):
        package = package.replace("package:", "")
        if len(package) > 0:
            experiences.append({"package": package, "name": package})

    experiences.sort(key=lambda el: el["name"])

    return experiences

@app.get("/loaded-experiences/{device_serial}")
async def loaded_experiences(request: Request, device_serial: str):
    # https://stackoverflow.com/a/53634311/960471
    return await _experiences(device_serial)


@app.get("/device-experiences/{device_serial}")
async def device_experiences(request: Request, device_serial: str):
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

    for device_serial in scan_devices():
        experiences = await _experiences(device_serial)

        experiences_map = {el["package"]: el["name"] for el in experiences}
        counter.update(experiences_map.keys())
        devices_lookup[device_serial] = experiences_map

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
    # https://stackoverflow.com/a/53634311/960471

    return templates.TemplateResponse(
        "experiences/device_experiences.html",
        {
            "request": request,
            "device": device_serial,
            "experiences": await _experiences(device_serial),
        },
    )


async def get_running_app(device_serial):
    current_app = adb_command(f"adb -s {device_serial} shell dumpsys activity activities | grep ResumedActivity".split(' ') )
    if current_app == '':
        return 'Unauthorized!'
    current_app = current_app.split(" ")[-2]
    return current_app.split("/")[0]


@app.post("/command/{command}/{device_serial}")
async def device_command(
    request: Request, command: str, device_serial: str, db: Session = Depends(get_db)
):

    #if device_serial != "ALL":
    try:
        my_json = await request.json()
    except ClientDisconnect:
        return {"success": False, "outcome": "Browser disconnected from backend unexpectantly"}

    try:
        experience = my_json["experience"]
    except KeyError:
        return {"success": False, "outcome": "No experience specified"}

    async def get_exp_info():
        cmd = f'adb -s {device_serial} shell dumpsys package | grep {experience} | grep Activity'.split(' ')
        my_info: str = adb_command(cmd)
        my_info = my_info.strip().splitlines()[0]
        if not my_info:
            return ""
        try:
            return my_info.split(" ")[1]
        except IndexError:
            return ""

    if command == "start":
        # https://stackoverflow.com/a/64241561/960471
        info = await get_exp_info()
        outcome = adb_command(f"adb -s {device_serial} shell am start -n {info}".split(' '))
        return {"success": "Starting" in outcome, "message": outcome}

    elif command == "stop":
        # https://stackoverflow.com/a/56078766/960471
        outcome = adb_command(f'adb -s {device_serial} shell am force-stop {experience}'.split(' '))
        launch_home_app(device_serial)
        return {"success": True}
    elif command == "copy-details":
        info: str = adb_command(f"adb -s {device_serial} shell dumpsys package | grep {experience} | grep Activity".split(' '))
        try:
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
            return {"success": True, 'message': 'Copied details to database!'}
        except IndexError:
            return {'success': False, 'message': 'There is an issue adding the details of this app to the database!'}

    elif command == "stop-some-experience":
        current_app = await get_running_app(device_serial)
        if current_app == "com.oculus.shellenv":
            return {"success": True, "outcome": "No app to stop!"}
        outcome = adb_command(f'adb -s {device_serial} shell am force-stop {current_app}'.split(' '))
        return {"success": True, "outcome": "Successfully stopped!"}

    ########### devices experiences menu
    elif command == "devices_experiences__stop_experience_some":
        my_devices = json.loads(my_json["devices"].replace("'", '"'))

        outcome = ""
        for device_serial in my_devices:
            outcome = adb_command(f'adb -s {device_serial} shell am force-stop {experience}'.split(' '))
            launch_home_app(device_serial)
        return {"success": True, "message": 'stopped the experience for some devices'}

    elif command == "devices_experiences__start_experience_some":
        my_devices = (
            my_json["devices"]
            .replace("[", "")
            .replace("]", "")
            .replace("'", "")
            .replace(" ", "")
        )
        devices_list = [x for x in my_devices.split(",") if len(x) > 0]

        # not that device_serial is defined at start of function and this is used within get_exp_info
        device_serial = devices_list[0]
        info = await get_exp_info()

        errs = []
        for device in devices_list:
            outcome = adb_command(f"adb -s {device} shell am start -n {info}".split(' '))

            if "Exception" in outcome:
                errs.append(f"An error occurred at device {device}: \n" + outcome)
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
    current_app = await get_running_app(device_serial)
    return {"current_app": current_app}
