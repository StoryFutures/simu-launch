import os
from turtle import up

from ppadb.client import Client as AdbClient
from ppadb.device import Device

from models_pydantic import Devices

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
HOME_APP_VERSION = "0.1"


def process_devices(client: AdbClient, payload: Devices):
    if payload.devices:
        return [Device(client, device) for device in payload.devices]
    return client.devices()


def launch_app(device, app_name, d_type: bool = False, command: str = None):
    """
        Launches an app on the specified device based on the device type and application name.

      :param device: the Device object for ppadb
      :param app_name: the application name, ie: com.simu-launch.calculator
      :param d_type: the device type, True = Quest, False = Android
      :param command: the command
      """

    if ".apk" in app_name:
        app_name = app_name[:-4]

    if d_type == 1:
        command = "am start -n " + app_name + "/" + command
    elif d_type == 2:
        command = "am start -n " + app_name
    else:
        command = "monkey -p " + app_name + " -v 1"
    print(command)

    print(device.shell(command),22)


def save_file(filename, data):
    apks = os.listdir("apks")
    if apks:
        delete_old = "apks/" + apks[0]
        os.remove(delete_old)

    with open("apks/" + filename, 'wb') as f:
        f.write(data)

def connect_actions(device: Device = None, volume: int = None,):
    """
        Applies any actions defined here to a device on initial connection.

    :param device: the Device object for ppadb.
    :param volume: the volume to set on the device.
    """
    try:
        if device is None:
            raise RuntimeError("No device present!")

        print("Performing initial connection setup..")

        device.shell(f'cmd media_session volume --stream 3 --set {str(volume)}')

        print(f'Device volume set to {volume}!')

        if "Unable to find" in device.shell("dumpsys package com.TrajectoryTheatre.SimuLaunchHome"):
            print("Home app not installed on device. Installing now..")
            device.install("apks/com.TrajectoryTheatre.SimuLaunchHome.apk")

        if HOME_APP_VERSION not in device.shell("dumpsys package com.TrajectoryTheatre.SimuLaunchHome | grep versionName"):
            print("Installed Home app isn't the latest version. Updating now..")
            device.install("apks/com.TrajectoryTheatre.SimuLaunchHome.apk")

        device.shell("am start -n com.TrajectoryTheatre.SimuLaunchHome/com.unity3d.player.UnityPlayerActivity")
        print("Launched home app!")
        print(f"Connect actions complete for {device.serial}")
    except RuntimeError as e:
        return {"success": False, "error": "An error occured: " + e.__str__()}

