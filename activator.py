import subprocess
import os
import time
import datetime
from dataclasses import dataclass

ips = ['192.168.0.100', '192.168.0.200', '192.168.1.101']
port = '8000'
sleep_time = 3
wait_time_s_for_connected_device_before_link_again = 60


@dataclass
class DeviceInfo:
    ip: str = ''
    last_connection: datetime = None
    remaining_connection_attempts = 3
    last_attempt_was_failure = False
    connected = False


class NoEndPointException(BaseException):
    pass


def adb_command(arr):
    outcome = subprocess.run(arr, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    message = outcome.stdout.decode('ascii')
    err = outcome.stderr.decode('ascii')
    if err:
        if 'Network is unreachable' in err:
            raise NoEndPointException
    return message

def adb_image(device):
    cmd = f'adb -s {device} shell screencap -p'.split(' ')
    outcome = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    message = outcome.stdout
    err = outcome.stderr.decode('ascii')
    if err:
        if 'Network is unreachable' in err:
            raise NoEndPointException
    return message


def alert(count, delay: float = 1.0):
    while count > 0:
        count -= 1
        subprocess.run([f"adb", "shell", "input", "keyevent", "26"], )
        time.sleep(delay)


def check(current_time: datetime = None,
          deviceinfo = None,
          sleep_time=sleep_time):
    if current_time is None:
        current_time = datetime.datetime.now()

    ip_address = adb_command(["adb", "shell", "ip", "route"])
    time_only = current_time.strftime("%H:%M:%S")
    print(f"{time_only}    {ip_address}")

    if not ip_address:
        alert(1, 3)
        if deviceinfo:
            deviceinfo.last_attempt_was_failure = True
            deviceinfo.remaining_connection_attempts -= 1
            if deviceinfo.remaining_connection_attempts == 0:
                deviceinfo = None
        return deviceinfo

    success = False
    if ip_address:
        alert(4, .5)
        if deviceinfo:
            if deviceinfo.ip != ip_address:
                deviceinfo = DeviceInfo(ip=ip_address)
        else:
            deviceinfo = DeviceInfo(ip=ip_address)

        # here we check if the device was connected in the last 60s. If so, dont do anything.
        # BUT, after 60s try to connect again
        if deviceinfo.connected:
            last_connected: datetime.timedelta = current_time - deviceinfo.last_connection
            if last_connected.seconds > wait_time_s_for_connected_device_before_link_again:
                deviceinfo = DeviceInfo(ip=ip_address)
            else:
                return deviceinfo

        deviceinfo.last_connection = current_time

        outcome = adb_command(["adb", "tcpip", "5555"])
        if "restarting in TCP mode port" not in outcome:
            print("err:", outcome)
        print('restarting in tcpip mode... waiting 3 seconds')
        time.sleep(sleep_time)
        print('letting storystarter know about Quest...')
        for ip in ips:

            commands = ["adb", "shell",
                        f"printf 'GET /connect HTTP/1.1\r\n http://{ip} \r\n\r\n'",
                        "|",
                        "nc",
                        '-w',
                        "3",
                        f"{ip} {port}"]
            try:
                outcome = adb_command(commands)
                print(f'response from endoint {ip}...' + outcome)
                if 'success' in outcome:
                    deviceinfo.connected = True
                    success = True
                    print(f'connected at endpoint {ip}')
                    alert(6, delay=.5)
                    return deviceinfo
            except NoEndPointException:
                print(f'cant find endpoint {ip}')

        if not success:
            print('Could not reach any endpoints!')
            # below, attempting to play error tones on the device
            # outcome = adb_command(["push" 'C:\Users\andy_\PycharmProjects\simu-launch\sounds\no_endpoint.wav', '/sdcard/Download/no_endpoint.wav'])

    return deviceinfo


if __name__ == "__main__":
    deviceinfo = None
    while True:
        deviceinfo = check(deviceinfo=deviceinfo)
        time.sleep(5)
