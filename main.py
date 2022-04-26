import re
import socket
import subprocess
from fastapi import FastAPI
from ppadb import InstallError
from starlette.requests import Request
from starlette.templating import Jinja2Templates
from ppadb.client import Client as AdbClient

app = FastAPI()

templates = Jinja2Templates("templates")

# Have some global variables to set app to run, devices, adb stuff etc.

global started_state

client = AdbClient(host="127.0.0.1", port=5037)
try:
    client.version()
    print('ADB server already initiated')
except RuntimeError:  # adb server probably not on
    # note ppadb does not offer ability to start server https://github.com/Swind/pure-python-adb/issues/36
    subprocess.call("adb version", shell=True)
    print('ADB server was initiated')
    pass

@app.get("/")
async def home(request: Request):
    """
        View mainly responsible for handling the front end, since nothing will happen on the backend at this endpoint.
    :param request: the Request() object
    :return: a TemplateResponse object containing the homepage
    """

    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/start")
async def start(request: Request):
    """
        Starts the experience on all devices

    :param request: The Request parameter
    :return: dictionary of all device serial numbers
    """

    client_list = client.devices()

    app_name = "com.amazon.calculator"

    try:
        for device in client_list:
            print(device.serial, app_name)
            # device.shell("monkey -p" + app_name + " -v 1")
            device.shell("am start -n" + "calculator")
    except InstallError as e:
        return {"success": False, "error": e.__str__()}

    return {"success": True, "started_app": app_name}

@app.get("/load")
async def load(request: Request):
    """
        Installs the experience on all devices

    :param request: the Request parameter
    :return: a success dictionary signifying the operation was successful
    """
    client_list = client.devices()

    apk_path = "apks/calculator.apk"

    apk_name = apk_path[4:]
    apk_name = apk_name[:4]

    try:
        for device in client_list:
            device.install(apk_path)
    except InstallError as e:
        return {"success": False, "error": e.__str__()}

    return {"success": True, "loaded_app": apk_name}

@app.get("/stop")
async def stop(request: Request):
    """
        Stops the experience on all devices

    :param request: The Request parameter
    :return: a dictionary containing the success flag of the operation and any errors
    """

    client_list = client.devices()

    app_name = "com.amazon.calculator"

    try:
        for device in client_list:
            print(device.serial)
            command = "am force-stop " + app_name
            print(command)
            device.shell(command)
            client.remote_disconnect(device)
    except InstallError as e:
        return {"success": False, "error": e.__str__()}

    return {"success": True, "stopped_app": app_name}

BASE_PORT = 5555

@app.get("/connect")
async def connect(request: Request):
    """
        Connects a device wirelessly to the server

    :param request: The Request parameter
    :return: a dictionary containing the success flag of the operation and any errors
    """

    devices = client.devices()

    device_ip = devices[0].shell("ip addr show wlan0")

    device_ip = device_ip[device_ip.find("inet "):]

    device_ip = device_ip[:device_ip.find("/24")]

    device_ip = device_ip[device_ip.find(" ")+1:]

    working = client.remote_connect(device_ip, port=BASE_PORT)

    return {"success": working}

