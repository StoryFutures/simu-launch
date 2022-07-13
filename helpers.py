import os

from adb_layer import scan_devices, adb_command
from models_pydantic import Devices

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
HOME_APP_VERSION = "0.1"
HOME_APP_APK = "com.TrajectoryTheatre.SimuLaunchHome.apk"
HOME_APP_ENABLED = False

def process_devices(payload: Devices):
    if payload.devices:
        return payload.devices
    return scan_devices()


def install(serial, apk_path):
    outcome = adb_command(['adb', '-s', {serial}, 'install', apk_path])
    return outcome


def launch_app(device_id, app_name, d_type: bool = False, command: str = None):
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

    return adb_command(['adb', 's', device_id] + command.split(' '))


def save_file(filename, data):
    apks = os.listdir("apks")
    if apks:
        delete_old = "apks/" + apks[0]
        os.remove(delete_old)

    with open("apks/" + filename, 'wb') as f:
        f.write(data)


def check_package(device_id, package):
    home_app_installed_info = adb_command(f"adb -s {device_id} dumpsys package {package}".split(' '))
    return "Unable to find" not in home_app_installed_info


def home_app_installed(device_id):
    return check_package(device_id, 'com.TrajectoryTheatre.SimuLaunchHome')


def connect_actions(device_serial: str, volume: int = None, ):
    """
        Applies any actions defined here to a device on initial connection.

    :param device: the Device object for ppadb.
    :param volume: the volume to set on the device.
    """
    try:

        print("Performing initial connection setup..")

        adb_command(f'adb -s {device_serial} cmd media_session volume --stream 3 --set {str(volume)}')

        print(f'Device volume set to {volume}!')

        timeout_hours = 4
        timeout = 60000 * 60 * timeout_hours  # 4 hours
        adb_command(f'adb -s {device_serial} shell settings put system screen_off_timeout {timeout}'.split(' '))
        print(f'Device screen timout set to {timeout_hours} hours!')

        if HOME_APP_ENABLED:
            if not home_app_installed(device_serial):
                print("Home app not installed on device. Installing now..")
                install(device_serial, "apks/" + HOME_APP_APK)

            device_info = f"adb -s {device_serial} dumpsys package com.TrajectoryTheatre.SimuLaunchHome | grep versionName"
            if HOME_APP_VERSION not in adb_command(device_info.split(' ')):
                print("Installed Home app isn't the latest version. Updating now..")
                install(device_serial, "apks/" + HOME_APP_APK)

            cmd = f"adb -s {device_serial} shell am start -n com.TrajectoryTheatre.SimuLaunchHome/com.unity3d.player.UnityPlayerActivity"
            adb_command(cmd.split(' '))
            print("Launched home app!")
            print(f"Connect actions complete for {device_serial}")
    except RuntimeError as e:
        return {"success": False, "error": "An error occured: " + e.__str__()}
