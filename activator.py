import subprocess
import os
import time
import datetime

ips = ['192.168.0.100', '192.168.0.200']
port = '8000'

while True:
    time_only = datetime.datetime.now().strftime("%H:%M:%S")
    ip_address = os.popen("adb shell ip route").read()
    print(f"{time_only} { ip_address}")
    if ip_address:
        ip_address = ip_address.split(" ")[8]

        os.system("adb tcpip 5555")

        payload = {
            'remote_address': ip_address
        }
        print('restarting in tcpip mode... waiting 3 seconds')
        time.sleep(3)
        print('letting storystarter know about Quest...')
        for ip in ips:
            commands = ["adb", "shell",
                        f"printf 'GET /connect HTTP/1.1\r\n http://{ ip } \r\n\r\n'",
                        "|",
                        "nc",
                        f"{ ip } { port }"]
            outcome = subprocess.run(commands, stdout=subprocess.PIPE).stdout.decode('ascii')
            if 'success' in outcome:
                print(11)

        print("Finished")
    time.sleep(5)
