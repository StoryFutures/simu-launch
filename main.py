import base64
import datetime
import json
import multiprocessing
import os
from functools import partial, wraps
import cv2
import numpy as np
from fastapi.encoders import jsonable_encoder
from fastapi_cache.backends.inmemory import InMemoryBackend
from ppadb.client import Client as AdbClient
from ppadb.client_async import ClientAsync as AdbClientAsync
from ppadb.device import Device
from ppadb.device_async import DeviceAsync
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from multiprocessing import Process, Pool, cpu_count
from fastapi import FastAPI, UploadFile, File, Form, Depends
from collections import Counter

from ppadb import InstallError
from starlette.requests import Request
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from helpers import launch_app, save_file, process_devices, connect_actions
from models_pydantic import Volume, Devices, Experience, NewExperience, StartExperience
from sql_app import models, crud
from sql_app.crud import get_all_apk_details, get_apk_details, set_device_icon, get_device_icon, crud_defaults
from sql_app.database import engine, SessionLocal
from sql_app.schemas import APKDetailsCreate, APKDetailsBase
from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache

models.Base.metadata.create_all(bind=engine)

app = FastAPI()
location = "/home/simu-launch/"
app.mount("/static", StaticFiles(directory=location + 'static'), name="static")
templates = Jinja2Templates(directory= location + 'templates')

simu_application_name = ""
global_volume = 10
HOME_APP_APK = "com.TrajectoryTheatre.SimuLaunchHome.apk"


icons = ['3-bars', '2-bars', '1-bar', 'circle-fill', 'square-fill', 'plus-lg', 'heart-fill', 'triangle-fill']
cols = ['red', 'pink', 'fuchsia', 'blue', 'green']

check_for_new_devices_poll_s = 8
defaults = {
    "screen_width": 192,
    "screen_height": 108,
    "check_for_new_devices_poll": check_for_new_devices_poll_s * 1000
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


def check_adb_running(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            client.devices()
        except RuntimeError as e:
            if e.__str__().find("Is adb running on your computer?"):
                print("ADB Server not running, starting it now!")
                command = os.system("adb start-server")
                print(command)
        return await func(*args, **kwargs)

    return wrapper


@app.post("/settings")
async def settings(screen_updates: int = Form(...),
                   db: Session = Depends(get_db)):
    crud.update_settings(db, screen_updates=screen_updates)
    crud_defaults(SessionLocal(), defaults)
    return {'success': True}

@app.get("/devices")
@cache(expire=check_for_new_devices_poll_s)
@check_adb_running
async def devices(db: Session = Depends(get_db)):
    """
        Gets a list of all devices connected via ADB.

    :return: a dict object containing a list of devices and any errors.
    """

    devices = []
    errs = []

    try:
        device: Device
        for device in client.devices():
            my_device_icon = get_device_icon(db, device.serial)
            devices.append({'id': str(device.serial), 'icon': my_device_icon})
    except RuntimeError as e:
        errs.append(str(e))
    return {'devices': devices, 'errs': errs}


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
        "home.html",
        {
            "request": request,
            "app_name": simu_application_name,
            "icons": icons,
            "cols": cols,
            "defaults": defaults
        },
    )

@app.get('/experiences')
async def experiences(request: Request, db: Session = Depends(get_db)):

    return templates.TemplateResponse(
        "experiences/set_experience_content.html",
        {
            "request": request,
            "choices": [item.apk_name for item in get_all_apk_details(db)],
        },
    )


@app.post("/start")
@check_adb_running
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
@check_adb_running
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

    try:
        for device in client_list:
            print("Installing " + apk_path + " on " + device.serial)
            p = Process(target=device.install, args=(apk_path,))
            p.start()
    except InstallError as e:
        return {"success": False, "error": e.__str__()}

    return {"success": True, "device_count": len(client_list)}


@app.post("/remove-remote-experience")
@check_adb_running
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
@check_adb_running
async def add_remote_experience(payload: NewExperience, db: Session = Depends(get_db)):
    """
        Adds a new experience, which has either been previously installed or is available on the device already.

    :param payload: a NewExperience object containing all necessary details for creating a new experience
    :param db: the database dependency
    :return: a success dictionary signifying the operation was successful
    """

    try:
        device_type = 0 if payload.command == "android" else 1

        item = APKDetailsBase(
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


@app.post("/stop")
@check_adb_running
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
            print("Stopped experience on device " + device.serial)
            command = "am force-stop " + app_name
            device.shell(command)
            # launch_app(device, app_name=HOME_APP_APK,d_type=True,command="com.unity3d.player.UnityPlayerActivity",)
    except RuntimeError as e:
        return {"success": False, "error": e.__str__()}

    return {"success": True, "stopped_app": app_name}


@app.post("/connect")
@check_adb_running
async def connect(request: Request):
    """
        Connects a device wirelessly to the server on port 5555. After the device is connected, it can be unplugged from
        the USB.

    :param request: The Request parameter which is used to receive the device data.
    :return: a dictionary containing the success flag of the operation and any errors
    """

    global BASE_PORT

    json = await request.json() if len((await request.body()).decode()) > 0 else {}

    remote_address = json["remote_address"] if "remote_address" in json else ""

    devices = client.devices()

    print("json ", json)
    print("address ", remote_address)

    if not remote_address:
        device_ip = devices[0].shell("ip addr show wlan0")
        device_ip = device_ip[device_ip.find("inet "):]
        device_ip = device_ip[: device_ip.find("/")]
        device_ip = device_ip[device_ip.find(" ") + 1:]
    else:
        device_ip = remote_address

    try:
        if not remote_address:
            os.system("adb -s" + devices[0].serial + " tcpip " + str(BASE_PORT))

        p = multiprocessing.Process(target=client.remote_connect, args=(device_ip, BASE_PORT))
        p.start()

        p.join(5)

        if not p.is_alive():
            connected_device = Device(client, device_ip)
            connect_actions(connected_device, global_volume,)

            print(
                "Established connection with client " + device_ip + ":" + str(BASE_PORT)
            )

            return {"success": True, "serial": device_ip}

        print("alive")
        raise RuntimeError(
            "Could not connect device. Make sure the device is connected on the same router as the server!")
    except RuntimeError as e:
        return {"success": False, "error": e.__str__()}


@app.post("/disconnect")
@check_adb_running
async def disconnect(payload: Devices):
    """
        Disconnects devices from the server.

    :devices: a list of devices to disconnect from
    :return: a dictionary containing the success flag of the operation and any errors
    """

    global BASE_PORT

    client_list = process_devices(client, payload)

    try:
        for device in client_list:
            print("Disconnecting device " + device.serial + " from server!")
            working = client.remote_disconnect(device.serial)
            if not working:
                print(1)
                return {
                    "success": False,
                    "error": "Encountered an error disconnecting device with ID/IP: "
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
@check_adb_running
async def screen_grab():
    """
        Gets a screenshot from every device.
    :param request: the Request object
    :return: a dictionary containing the success flag
    """

    devices = client.devices()

    screen_caps_folder = "screenshots/"

    try:
        folder = (
                screen_caps_folder + datetime.datetime.now().strftime("%m%d%Y%H%M%S") + "/"
        )
        os.makedirs(folder)
        i = 0
        for device in devices:
            result = device.screencap()
            with open(folder + "screen" + str(i) + ".png", "wb") as fp:
                fp.write(result)
            i += 1
    except RuntimeError as e:
        return {"success": False, "errors": e.__str__()}

    return {"success": True}


@app.post("/volume")
@check_adb_running
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
        try:
            device.shell(f'cmd media_session volume --stream 3 --set {payload.volume}')
            device.shell(f'media volume --stream 3 --set {payload.volume}')
        except RuntimeError as e:
            fails.append(e)

    if fails:
        return {"success": False, "fails": str(fails)}

    return {"success": True}


my_devices = None
screen_shots_cache = {}


async def check_image(device_serial, refresh_ms, size):
    async def gen_image():

        device: DeviceAsync = await client_async.device(device_serial)

        im = await device.screencap()
        if im:
            image = cv2.imdecode(np.frombuffer(im, np.uint8), cv2.IMREAD_COLOR)

            if screen_shots_cache[device_serial]['quest']:
                image = image[0:image.shape[0], 0: int(image.shape[1] * .5)]

            height = image.shape[0]
            width = int(image.shape[1] / height * defaults['screen_height'])
            height = defaults['screen_height']

            dsize = (width, height)
            image = cv2.resize(image, dsize)

            _, encoded_img = cv2.imencode('.png', image)
            return base64.b64encode(encoded_img).decode("utf-8")
        return None

    timestamp = datetime.datetime.now()

    if device_serial not in screen_shots_cache:
        info = client.device(device_serial).list_features()
        screen_shots_cache[device_serial] = {'info': info,
                                             'quest': 'oculus.hardware.standalone_vr' in info, }

    if size not in screen_shots_cache[device_serial]:
        ancient = datetime.datetime.now() - datetime.timedelta(hours=10)
        screen_shots_cache[device_serial][size] = {'timestamp': ancient, 'file_id': None}
    if screen_shots_cache[device_serial][size]['timestamp'] + datetime.timedelta(
            milliseconds=refresh_ms) < timestamp:
        screen_shots_cache[device_serial][size]['timestamp'] = timestamp
        try:
            image = await gen_image()
            if image:
                screen_shots_cache[device_serial][size]['file_id'] = image
        except RuntimeError:
            return False

    return True


@app.get("/device-screen/{refresh_ms}/{size}/{device_serial}")
@check_adb_running
async def devicescreen(request: Request, refresh_ms: int, size: str, device_serial: str):
    success = await check_image(device_serial, refresh_ms, size)

    if not success:
        return {'success': False}

    image = screen_shots_cache[device_serial][size]['file_id']

    return {'base64_image': image}


@app.get("/battery/{device_serial}")
@check_adb_running
async def battery(device_serial: str):
    device: Device = client.device(device_serial)
    if device is None:  # issue with device being unplugged
        return 0
    return device.get_battery_level()


async def _experiences(device_serial: str = None, device: Device = None) -> []:
    if device is None:
        device: Device = client.device(device_serial)

    payload = device.shell('cmd package list packages -3').strip()

    experiences = []

    print(payload)
    for package in payload.split('\n'):
        package = package.replace('package:', '')
        experiences.append({'package': package, 'name': package})

    experiences.sort(key=lambda el: el['name'])

    return experiences

@app.get("/device-experiences/{device_serial}")
@check_adb_running
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
@check_adb_running
async def devices_experiences(request: Request):

    # https://stackoverflow.com/a/53634311/960471

    devices = {}
    counter = Counter()

    for device in client.devices():
        experiences = await _experiences(device=device)
        experiences_map = {el['package']: el['name'] for el in experiences}
        counter.update(experiences_map.keys())
        devices[device.serial] = experiences_map

    combined = {}
    for experience in [key for key, val in counter.most_common()]:
        row = []
        for device_id, experience_map in devices.items():
            if experience in experience_map:
                row.append(device_id)
            else:
                row.append('')
        combined[experience] = row


    return templates.TemplateResponse(
        "experiences/devices_experiences.html",
        {
            "request": request,
            "combined": combined,
        },
    )


@app.get("/device-experiences/{device_serial}")
@check_adb_running
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

@app.post("/command/{command}/{device_serial}")
@check_adb_running
async def device_command(request: Request, command: str, device_serial: str, db: Session = Depends(get_db)):
    device = None
    if device_serial != 'ALL':
        device = await client_async.device(device_serial)

    json = await request.json()
    experience = json['experience']

    async def get_exp_info(_d: Device):
        my_info: str = await _d.shell(f'dumpsys package | grep {experience} | grep Activity')
        my_info = my_info.strip().split('\n')[0]
        if not my_info:
            return ''
        return my_info.split(' ')[1]

    if command == 'start':
        # https://stackoverflow.com/a/64241561/960471
        info = await get_exp_info(device)
        outcome = await device.shell(f"am start -n {info}")
        print(111, outcome)
        return {'success': 'Starting' in outcome}
    elif command == 'start_experience_some':
        my_devices = json['devices'].replace('[', "").replace(']', "").replace("'", "").replace(' ', '')
        devices_list = [x for x in my_devices.split(',') if len(x) > 0]

        info = await get_exp_info(await client_async.device(devices_list[0]))
        for d in devices_list:
            d: DeviceAsync = await client_async.device(d)
            outcome = await d.shell(f"am start -n {info}")

            if "Exception" in outcome:
                print(f"An error occured at device {d.serial}: \n" + outcome)
                return {"success": False, "error": "Couldn't start experience on device " + d.serial + "! Make sure a boundary is setup."}

        return {'success': True}
    elif command == 'stop':
        # https://stackoverflow.com/a/56078766/960471
        await device.shell(f"am force-stop {experience}")
        return {'success': True}
    elif command == 'copy-details':
        info: str = await device.shell(f'dumpsys package | grep {experience} | grep Activity')
        print(info,22)
        info = info.strip().split('\n')[0]
        info = info.split(' ')[1]
        print(info)
        item = APKDetailsBase(
            apk_name=info,
            device_type=2,
            command='',
        )

        crud.create_apk_details_item(
            db=db, item=APKDetailsCreate.parse_obj(item.dict())
        )
        return {'success': True}
    elif command == 'stop_experience_some':
        my_devices = json['devices'].replace('[', "").replace(']', "").replace("'", "").replace(' ', '')
        devices_list = [x for x in my_devices.split(',') if len(x) > 0]
        for d in devices_list:
            d: DeviceAsync = await client_async.device(d)
            await d.shell(f"am force-stop {experience}")
        return {'success': True}
    elif command == 'stop_some_experience':

        await device.shell(f"am force-stop {experience}")

        return {'success': True, 'outcome': 'Successfully stopped!'}
    else:
        return {'success': True, 'outcome': 'No experience was running'}


@app.post("/set-device-icon/{device_serial}")
async def device_icon(request: Request, device_serial: str, db: Session = Depends(get_db)):
    json = await request.json()
    col = json['col']
    icon = json['icon']
    set_device_icon(db=db, device_id=device_serial, icon=icon, col=col)
    return {'success': True}
