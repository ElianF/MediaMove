import datetime
import json
import pathlib
import re
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
            dev = AdbDeviceTcp(ip)
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
        remoteConfig = pathlib.Path('/sdcard', 'MediaMove', f'{name}.json')
        localConfig = pathlib.Path('.tmp', f'{self.serialno}_{name}.json')

        if 1 == self().shell(f'test -e {remoteConfig.parent}; echo $?'):
            self().shell(f'mkdir {remoteConfig.parent}')
        
        if 1 == self().shell(f'test -e {remoteConfig}; echo $?'):
            localConfig.write_text(json.dumps([template], indent=4))
        else:
            if not localConfig.exists():
                self().pull(str(remoteConfig), localConfig)

            content = json.loads(localConfig.read_bytes())
            if template not in content:
                content.append(template)
                localConfig.write_text(json.dumps(content, indent=4))


    def saveConfig(self):
        name = socket.gethostname()
        remoteConfig = pathlib.Path('/sdcard', 'MediaMove', f'{name}.json')
        localConfig = pathlib.Path('.tmp', f'{self.serialno}_{name}.json')

        content = json.loads(localConfig.read_bytes())
        localConfig.write_text(json.dumps(content, indent=4))

        self().push(localConfig, str(remoteConfig), mtime=int(localConfig.stat().st_mtime))
        localConfig.unlink()
    

    def fetch(self):
        name = socket.gethostname()
        localConfig = pathlib.Path('.tmp', f'{self.serialno}_{name}.json')
        tree = pathlib.Path('/sdcard', 'MediaMove', f'{name}_tree')
        newtree = pathlib.Path('/sdcard', 'MediaMove', f'{name}_newtree')
        changes = dict()
        groupPattern = '([ +-])(.*?):\n(?:[ +-]total \d+\n)?((?:.|\n)*)'
        timePat = '\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}.\d+? [ +-]\d{4}'
        filePattern = '([+-])(.).*? (\d+) (' + timePat +') (.*)'

        syncDirs = [sync['remote'] for sync in json.loads(localConfig.read_bytes())]
        syncDirs.remove('')

        if '1' == self().shell('test -e {tree}; echo $?').replace('\n', ''):
            self().shell(f'touch {tree}')
        
        out = self().shell(fr'ls -RAlt -og --full-time {" ".join(map(str, syncDirs))} > {newtree}; diff -u {tree} {newtree} | grep -e ":$" -e "^[+-]"')
        
        out = out.split('\n', maxsplit=2)[2]
        out = re.sub('\s{2,}', ' ', out)

        for part in out.split('\n+\n'):
            dirSign, dir, changesStr = re.findall(groupPattern, part)[0]
            
            if dirSign != ' ':
                if all(map(lambda parent: str(parent) not in changes, [pathlib.Path(dir)]+list(pathlib.Path(dir).parents))):
                    changes[dir] = dirSign
                continue
        
            changes[dir] = list()
            lookup = list()
            for change in changesStr.split('\n'):
                sign, dirBit, size, timeStr, title = re.findall(filePattern, change)[0]

                if dirBit == 'd':
                    changes[title] = sign
                    continue
                
                bundle = [
                    sign, 
                    int(size), 
                    datetime.datetime.fromisoformat(timeStr), 
                    title
                ]
                
                if title in lookup:
                    if bundle[0] == '-':
                        bundle = changes[dir][lookup.index(title)]
                    bundle[0] = '~'
                    del changes[dir][lookup.index(title)]

                lookup.append(title)
                changes[dir].append(bundle)

        return changes