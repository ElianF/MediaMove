import datetime
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
        if '1' == self.execute(f'test -e "{self.tree.absolute()}"; echo $?').replace('\n', ''):
            self.execute(f'touch "{self.tree.absolute()}"')
        
        syncDirs = '" "'.join(map(str, self.syncDirs()))
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
        content = self.remote.execute(f'cat "{self.remote.config}"')
        syncDirs = [sync['local'] for sync in json.loads(content)]
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
        content = self().shell(f'cat {self.config}')
        syncDirs = [sync['remote'] for sync in json.loads(content)]
        syncDirs.remove('')

        return syncDirs
    

    def __call__(self, wake=False):
        if self.wired != None:
            dev = self.wired
        else:
            dev = self.wireless
            if wake: dev.shell('input keyevent KEYCODE_WAKEUP')
        return dev

    
    def connectWired(self, signer, retry=False):
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
            self.wired = dev
            self.serialno = dev.shell('getprop ro.boot.serialno').replace('\n', '')
            self.ip = dev.shell('ip addr show wlan0 | grep "inet " | cut -d " " -f 6 | cut -d / -f 1')[:-1]
        

    def connectWireless(self, signer, ip):
        self.wireless = None
        try:
            dev = AdbDeviceTcp(ip)
            dev.connect(rsa_keys=[signer], auth_timeout_s=0.1)
        
        except Exception as e:
            print("[2] Warning, exception occurred:", type(e).__name__, "–", e)
        
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