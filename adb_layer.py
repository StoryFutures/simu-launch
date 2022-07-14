import subprocess
from collections import namedtuple


class NoEndPointException(BaseException):
    pass


def adb_command(arr):
    outcome = subprocess.run(arr, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
    message = outcome.stdout.decode('ascii')
    err = outcome.stderr.decode('ascii')
    if err:
        if 'Network is unreachable' in err:
            raise NoEndPointException
    return message


def adb_command_no_wait(arr):
    """Substantially faster than the above command as it does not wait for any response"""
    subprocess.Popen(arr)


def adb_image(device):
    cmd = f'adb -s {device} shell screencap -p'.split(' ')
    outcome = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    message = outcome.stdout
    err = outcome.stderr.decode('ascii')
    if err:
        if 'Network is unreachable' in err:
            raise NoEndPointException
    return message


def scan_devices():
    outcome = adb_command(["adb", "devices"])
    alive = [serial.split('\t')[0] for serial in outcome.splitlines()[1:] if 'offline' not in serial and serial]
    return alive


DeviceState = namedtuple('DeviceState', ['serial', 'state'])


def scan_devices_and_state():
    outcome = adb_command(["adb", "devices"])
    alive = []
    for serial in outcome.splitlines()[1:]:
        if serial:
            alive.append(DeviceState(*serial.split('\t')))
    return alive
