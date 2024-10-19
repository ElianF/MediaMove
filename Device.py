import json
import pathlib
import subprocess
import time
import socket

from adb_shell.adb_device import AdbDeviceTcp, AdbDeviceUsb
from adb_shell.exceptions import UsbDeviceNotFoundError


class Device:
    def __init__(self):
        self.wired = None
        self.serialno = None
        self.ip = None

        self.wireless = None
    

    def __call__(self):
        if self.wired != None:
            return self.wired
        else:
            return self.wireless

    
    def connectWired(self, signer):
        self.wired = None
        try:
            dev = AdbDeviceUsb()
            dev.connect(rsa_keys=[signer], auth_timeout_s=0.1)
            if '5555' != dev.shell('getprop service.adb.tcp.port').replace('\n', ''):
                dev.close()
                subprocess.run('adb disconnect && adb tcpip 5555 && adb kill-server && echo done', shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                time.sleep(5)
                dev = AdbDeviceUsb()
                dev.connect(rsa_keys=[signer], auth_timeout_s=0.1)
        except UsbDeviceNotFoundError:
            pass
        except Exception as e:
            print("Warning, exception occurred:", type(e).__name__, "–", e)
        else:
            self.wired = dev
            self.serialno = dev.shell('getprop ro.boot.serialno').replace('\n', '')
            self.ip = dev.shell('ip addr show wlan0 | grep "inet " | cut -d " " -f 6 | cut -d / -f 1')[:-1]
        

    def connectWireless(self, signer, ip):
        self.wireless = None
        try:
            dev = AdbDeviceTcp(ip, default_transport_timeout_s=9.)
            dev.connect(rsa_keys=[signer], auth_timeout_s=0.1)
        except Exception as e:
            print("Warning, exception occurred:", type(e).__name__, "–", e)
        else:
            self.wireless = dev
            self.serialno = dev.shell('getprop ro.boot.serialno').replace('\n', '')
            self.ip = dev.shell('ip addr show wlan0 | grep "inet " | cut -d " " -f 6 | cut -d / -f 1')[:-1]
        

    def disconnect(self):
        if self.wired != None:
            self.wired.close()
        if self.wireless != None:
            self.wireless.close()


    def loadConfig(self):
        template = {
            "uniqueLocal": "copy/move/delete/ignore",
            "newLocal": "updateLocal/updateRemote/ignore",
            "newRemote": "updateLocal/updateRemote/ignore",
            "uniqueRemote": "copy/move/delete/ignore",
            "local": "",
            "remote": "",
            "excl": []
        }
        
        name = socket.gethostname()
        remotePath = pathlib.Path('/sdcard', 'MediaMove', f'{name}.json')
        localPath = pathlib.Path('.tmp', f'{self.serialno}_{name}.json')

        if 1 == self().shell(f'test -e {remotePath.parent}; echo $?'):
            self().shell(f'mkdir {remotePath.parent}')
        
        if 1 == self().shell(f'test -e {remotePath}; echo $?'):
            localPath.write_text(json.dumps([template], indent=4))
        else:
            if not localPath.exists():
                self().pull(str(remotePath), localPath)

            content = json.loads(localPath.read_bytes())
            if template not in content:
                content.append(template)
                localPath.write_text(json.dumps(content, indent=4))


    def saveConfig(self):
        name = socket.gethostname()
        remotePath = pathlib.Path('/sdcard', 'MediaMove', f'{name}.json')
        localPath = pathlib.Path('.tmp', f'{self.serialno}_{name}.json')

        content = json.loads(localPath.read_bytes())
        localPath.write_text(json.dumps(content, indent=4))

        self().push(localPath, str(remotePath), mtime=int(localPath.stat().st_mtime))
        localPath.unlink()