import datetime
import io
import json
import pathlib
import re
import subprocess
import time
import socket
from abc import abstractmethod

from adb_shell.adb_device import AdbDeviceTcp, AdbDeviceUsb


class Device:
    @abstractmethod
    def execute(self, cmd:str, *args) -> str: raise NotImplementedError
    @abstractmethod
    def syncDirs(self) -> list: raise NotImplementedError
    

    def fetch(self):
        if '1\n' == self.execute(f'test -e "{self.tree.absolute()}"; echo $?'):
            self.execute(f'touch "{self.tree.absolute()}"')
        
        syncDirs = '" "'.join(map(str, self.syncDirs()))
        if syncDirs == '':
            return ''
        out = self.execute(f'ls -RAlt -og --full-time "{syncDirs}" > "{self.newtree.absolute()}"; diff -u "{self.tree.absolute()}" "{self.newtree.absolute()}" | grep -e ":$" -e "^[+-]"')
        
        out = out.split('\n', maxsplit=2)[2]
        out = re.sub('\s{2,}', ' ', out)

        return out

    
    def iterateFileChanges(self, changesStr:str):
        timePat = '\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}.\d+? [ +-]\d{4}'
        filePattern = '([+-])(.).*? (\d+) (' + timePat +') (.*)'
        
        ret = list()
        lookup = list()

        for change in changesStr.split('\n'):
            sign, dirBit, size, timeStr, title = re.findall(filePattern, change)[0]

            if dirBit == 'd':
                self.changes[title] = sign
                continue
            
            bundle = [
                sign, 
                int(size), 
                datetime.datetime.fromisoformat(timeStr), 
                title
            ]
            
            if title in lookup:
                if bundle[0] == '-':
                    bundle = ret[lookup.index(title)]
                bundle[0] = '~'
                del ret[lookup.index(title)]

            lookup.append(title)
            self.changes[dir].append(bundle)

        return ret


    def getChanges(self):
        groupPattern = '([ +-])(.*?):\n(?:[ +-]\w+? \d+\n)?((?:.|\n)*)'

        for group in self.fetch().split('\n+\n'):
            if group == '':
                break

            dirSign, dir, changesStr = re.findall(groupPattern, group)[0]
            
            if dirSign == ' ':
                self.changes[dir] = self.iterateFileChanges(changesStr)
            
            elif all(map(lambda parent: str(parent) not in self.changes, [pathlib.Path(dir)]+list(pathlib.Path(dir).parents))):
                self.changes[dir] = dirSign
        
        return self.changes


class Host(Device):
    def __init__(self, remote:Device):
        self.changes = dict()
        self.remote:PortableDevice = remote
        
        self.tree = pathlib.Path('.tmp', remote.serialno, 'tree')
        self.newtree = pathlib.Path('.tmp', remote.serialno, 'newtree')

        if not self.tree.exists():
            self.tree.parent.mkdir(exist_ok=True)
            self.tree.write_text('')


    def execute(self, cmd:str, *args) -> str:
        return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, encoding='utf-8').stdout # TODO: add args parameters


    def syncDirs(self) -> list:
        content = self.remote.loadConfig()
        syncDirs = [sync['local'] for sync in content]
        syncDirs.remove('')

        return syncDirs


class StationaryDevice(Device):
    pass


class PortableDevice(Device):
    def __init__(self):
        self.changes = dict()

        self.wired = None
        self.serialno = None
        self.ip = None

        self.wireless = None

        name = socket.gethostname()
        self.config = pathlib.Path('/sdcard', 'MediaMove', f'{name}.json')
        self.tree = pathlib.Path('/sdcard', 'MediaMove', f'{name}_tree')
        self.newtree = pathlib.Path('/sdcard', 'MediaMove', f'{name}_newtree')
    

    def execute(self, cmd:str, *args) -> str:
        return self(wake=True).shell(cmd) # TODO: avoid waking up device every time 
    

    def syncDirs(self) -> list:
        content = self.loadConfig()
        syncDirs = [sync['remote'] for sync in content]
        syncDirs.remove('')

        return syncDirs
    

    def __call__(self, wake=False):
        if self.wired != None:
            device = self.wired
        else:
            device = self.wireless
            if wake: device.shell('input keyevent KEYCODE_WAKEUP')
        return device

    
    def connectWired(self, signer, retry=False):
        self.wired = None
        try:
            device = AdbDeviceUsb()
            device.connect(rsa_keys=[signer], auth_timeout_s=0.1)
            if '5555\n' != device.shell('getprop service.adb.tcp.port'):
                device.close()
                subprocess.run('adb disconnect && adb tcpip 5555 && adb kill-server && echo done', shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                time.sleep(5)
                device = AdbDeviceUsb()
                device.connect(rsa_keys=[signer], auth_timeout_s=0.1)
        
        except Exception as err:
            if type(err).__name__ in ['UsbDeviceNotFoundError']:
                pass
            elif type(err).__name__ == 'USBErrorBusy':
                if not retry:
                    subprocess.run('adb kill-server', shell=True)
                    time.sleep(5)
                    self.connectWired(signer, retry=True)
                else:
                    print("[3] Warning, exception occurred:", type(err).__name__, "–", err)
            else:
                print("[1] Warning, exception occurred:", type(err).__name__, "–", err)
        
        else:
            self.wired = device
            self.serialno = device.shell('getprop ro.boot.serialno').replace('\n', '')
            self.ip = device.shell('ip addr show wlan0 | grep "inet " | cut -d " " -f 6 | cut -d / -f 1')[:-1]
        

    def connectWireless(self, signer, ip):
        self.wireless = None
        try:
            device = AdbDeviceTcp(ip)
            device.connect(rsa_keys=[signer], auth_timeout_s=0.1)
        
        except Exception as e:
            print("[2] Warning, exception occurred:", type(e).__name__, "–", e)
        
        else:
            self.wireless = device
            self.serialno = device.shell('getprop ro.boot.serialno').replace('\n', '')
            self.ip = device.shell('ip addr show wlan0 | grep "inet " | cut -d " " -f 6 | cut -d / -f 1')[:-1]
        

    def disconnect(self):
        if self.wired != None:
            self.wired.close()
        if self.wireless != None:
            self.wireless.close()


    def loadConfig(self) -> list[dict]:
        template = {
            "uniqueLocal": "copy/move/delete/ignore",
            "newLocal": "updateLocal/updateRemote/ignore",
            "newRemote": "updateLocal/updateRemote/ignore",
            "uniqueRemote": "copy/move/delete/ignore",
            "local": "",
            "remote": "",
            "excl": []
        }

        if '1\n' == self().shell(f'test -e {self.config.parent}; echo $?'):
            self().shell(f'mkdir {self.config.parent}')
        
        if '1\n' == self().shell(f'test -e {self.config}; echo $?'):
            content = list()
        else:
            content = json.loads(self().shell(f'cat {self.config}'))

        if template not in content:
            content.append(template)
        
            buffer = io.BytesIO(bytes(json.dumps(content, indent=4), 'utf-8'))
            self().push(buffer, self.config)
        
        return content