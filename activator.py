import requests
import os
import time
import datetime
while True:
    time_only = datetime.datetime.now().strftime("%H:%M:%S")
    ip_address = os.popen("adb shell ip route").read()
    print(f"{time_only} { ip_address}")
    if ip_address:
        ip_address = ip_address.split(" ")[8]
        print(ip_address)

        os.system("adb tcpip 5555")

        payload = {
            'remote_address': ip_address
        }
        print('restarting in tcpip mode... waiting 3 seconds')
        time.sleep(3)
        print('letting storystarter know about Quest...')
        outcome = os.popen("""adb shell "printf 'GET /connect HTTP/1.1\r\n http://192.168.0.155 \r\n\r\n' | nc 192.168.0.155 8000""").read()
        print(outcome,222)

        print("Finished")
    time.sleep(5)