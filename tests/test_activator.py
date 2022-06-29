import os
from unittest import TestCase, mock
from unittest.mock import patch

from activator import check, DeviceInfo


@patch("activator.adb_command")
def test_not_connected(adb_command):
    adb_command.return_value = ''
    assert check() == None


@patch("activator.adb_command")
def test_not_connected_but_has_past_device(adb_command):
    adb_command.return_value = ''
    deviceinfo: DeviceInfo = DeviceInfo(ip='123')
    assert check(deviceinfo=deviceinfo) == deviceinfo
    assert check(deviceinfo=deviceinfo) == deviceinfo
    assert check(deviceinfo=deviceinfo) == None


@patch("activator.adb_command")
def test_connects_but_has_existing_device(adb_command):
    adb_command.return_value = '345'
    deviceinfo: DeviceInfo = DeviceInfo(ip='123')
    deviceinfo2: DeviceInfo = check(deviceinfo=deviceinfo, sleep_time=0)
    assert deviceinfo2 != deviceinfo
    assert deviceinfo2.ip == '345'