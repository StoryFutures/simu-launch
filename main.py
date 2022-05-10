import datetime
import os
import random
import tempfile
from functools import partial
from multiprocessing import Process, Pool, cpu_count

import cv2
import numpy as np
from fastapi import FastAPI
from ppadb import InstallError
from ppadb.client import Client as AdbClient
from ppadb.device import Device
from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# Have some global variables to set app to run, devices, adb stuff etc.

global started_state

client = AdbClient(host="127.0.0.1", port=5037)


def check_adb_running():
  try:
    devices = client.devices()

  except RuntimeError as e:
    if e.__str__().find("Is adb running on your computer?"):
      print("ADB Server not running, starting it now!")
      command = os.system("adb start-server")
      print(command)


def launch_app(device, app_name):
  # command = am start -n com.package.name/com.package.name.MainActivity or UnityPlayerActivity
  device.shell("monkey -p" + app_name + " -v 1")


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
      Starts the experience on all devices through the adb shell commands.

  :param request: The Request parameter
  :return: dictionary of all device serial numbers
  """

  check_adb_running()

  client_list = client.devices()

  vr_app_name = "com.alturgames.BendingOaksVR/com.unity3d.player.UnityPlayerActivity"
  android_app_name = "com.amazon.calculator"

  try:
    pool = Pool(cpu_count())
    launch_func = partial(launch_app, app_name=android_app_name)
    results = pool.map(launch_func, client_list)
    pool.close()
    pool.join()
  except RuntimeError as e:
    return {"success": False, "error": e.__str__()}

  return {"success": True, "device_count": len(client_list)}


@app.get("/load")
async def load(request: Request):
  """
      Installs the experience on all devices

  :param request: the Request parameter
  :return: a success dictionary signifying the operation was successful
  """

  check_adb_running()
  client_list = client.devices()

  apk_path = "apks/calculator.apk"

  apk_name = apk_path[4:]
  apk_name = apk_name[:4]

  try:
    for device in client_list:
      print("Installing " + apk_path + " on " + device.serial)
      p = Process(target=device.install, args=(apk_path,))
      p.start()
  except InstallError as e:
    return {"success": False, "error": e.__str__()}

  return {"success": True, "device_count": len(client_list)}


@app.get("/stop")
async def stop(request: Request):
  """
      Stops the experience on all devices through ADB shell commands

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
  except RuntimeError as e:
    return {"success": False, "error": e.__str__()}

  return {"success": True, "stopped_app": app_name}


BASE_PORT = 5555


@app.get("/connect")
async def connect(request: Request):
  """
      Connects a device wirelessly to the server on port 5555. After the device is connected, it can be unplugged from
      the USB.

  :param request: The Request parameter
  :return: a dictionary containing the success flag of the operation and any errors
  """

  global BASE_PORT

  check_adb_running()

  devices = client.devices()

  device_ip = devices[0].shell("ip addr show wlan0")

  device_ip = device_ip[device_ip.find("inet "):]

  device_ip = device_ip[:device_ip.find("/")]

  device_ip = device_ip[device_ip.find(" ") + 1:]

  try:
    os.system("adb -s" + devices[0].serial + " tcpip " + str(BASE_PORT))
    working = client.remote_connect(device_ip, port=BASE_PORT)

    if working:
      print("Established connection with client " + device_ip + ":" + str(BASE_PORT))

      return {"success": True, "serial": devices[0].serial}

    return {"success": False}
  except RuntimeError as e:
    return {"success": False, "error_log": e.__str__()}


@app.get("/exit-server")
async def exit_server(request: Request):
  """
      Kills the ADB server and all connections with devices. Essentially a system shutdown, where the FastAPI backend
      remains alive.
  :param request: the Request object
  :return: a dictionary containing the success flag
  """

  try:
    result = client.kill()
  except RuntimeError as e:
    return {"success": False, "errors": e.__str__()}

  return {"success": result}


@app.get("/screen-grab")
async def screen_grab(request: Request):
  """
      Gets a screenshot from every device.
  :param request: the Request object
  :return: a dictionary containing the success flag
  """

  check_adb_running()

  devices = client.devices()

  screen_caps_folder = "screenshots/"

  try:
    folder = screen_caps_folder + datetime.datetime.now().strftime("%m%d%Y%H%M%S") + "/"
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


my_devices = None
screen_shots_cache = {}


# screen_shots_cache ={ device_id: { abvde: {size1: {timestamp: x, file_id: y }}}}

def readimage(path):
  count = os.stat(path).st_size / 2
  with open(path, "rb") as f:
    return bytearray(f.read())


@app.get("/screen/{refresh_ms}/{size}/{device_serial}/{cache_blocker}.png")
async def screen(request: Request, refresh_ms: int, size: str, device_serial: str, cache_blocker: str):
  def gen_image():
    with tempfile.NamedTemporaryFile(mode="w+b", suffix=".png", delete=False) as FOUT:
      device: Device = my_devices[device_serial]
      im = device.screencap()

      img = cv2.imdecode(np.frombuffer(im, np.uint8), cv2.IMREAD_COLOR)
      cv2.imshow("", img)
      iName = "".join([str(FOUT.name), ".png"])
      cv2.imwrite(iName, img)


      return FOUT.name

  timestamp = datetime.datetime.now()

  if device_serial not in screen_shots_cache:
    screen_shots_cache[device_serial] = {}

  if size not in screen_shots_cache[device_serial]:
    ancient = datetime.datetime.now() - datetime.timedelta(hours=10)
    screen_shots_cache[device_serial][size] = {'timestamp': ancient, 'file_id': None}

  if screen_shots_cache[device_serial][size]['timestamp'] + datetime.timedelta(
          milliseconds=refresh_ms) < timestamp:
    screen_shots_cache[device_serial][size]['timestamp'] = timestamp
    screen_shots_cache[device_serial][size]['file_id'] = gen_image()

  return FileResponse(screen_shots_cache[device_serial][size]['file_id'], media_type="image/png")


@app.get("/device-screen/{refresh_ms}/{size}/{device_serial}/")
async def devicescreen(request: Request, refresh_ms: int, size: str, device_serial: str):
  cache_blocker = random.randint(0, 10000000)
  return templates.TemplateResponse("htmx/device.html", {"request": request, "device_serial": device_serial,
                                                         'cache_blocker': str(cache_blocker)})


@app.get("/linkup")
async def linkup(request: Request):
  check_adb_running()
  global my_devices
  my_devices = {device.serial: device for device in client.devices()}

  return templates.TemplateResponse("htmx/devices.html", {"request": request, "devices": client.devices()})
