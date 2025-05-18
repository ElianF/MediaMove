import datetime
import io
import json
import pathlib
import re
import subprocess
import time
from abc import abstractmethod
import uuid

from adb_shell.adb_device import AdbDeviceTcp, AdbDeviceUsb


class Device:
    @abstractmethod
    def execute(self, cmd:str, *args) -> str: raise NotImplementedError
    @abstractmethod
    def syncDirs(self) -> list: raise NotImplementedError
    @abstractmethod
    def id(self) -> str: raise NotImplementedError
    

    def fetch(self):
        if '' != self.execute(f'ls "{self.tree}" 3>&2 2>&1 1>&3'):
            self.execute(f'touch "{self.tree}"')
        
        syncDirs = '" "'.join(map(str, self.syncDirs()))
        if syncDirs == '':
            return ''
        out = self.execute(f'ls -RAlt --full-time "{syncDirs}" > "{self.newtree}" && diff "{self.tree}" "{self.newtree}" | grep -e ":$" -e "^[+-]"', keepLinebreaks=True)
        
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
            break
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
        self.remote:Device = remote
        
        self.mac, self.user, self.name, self.ip, self.os = self.retrieveCharacteristics()

        self.tree = pathlib.Path('.tmp', remote.id(), 'tree')
        self.newtree = pathlib.Path('.tmp', remote.id(), 'newtree')

        if not self.tree.exists():
            self.tree.parent.mkdir(exist_ok=True)
            self.tree.write_text('')


    def execute(self, cmd:str, keepLinebreaks:bool=False) -> str:
        out = subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.PIPE, encoding='utf-8').stdout # TODO: add args parameters
        if not keepLinebreaks:
            out = out.replace('\n', '')
        return out


    def syncDirs(self) -> list:
        content = self.remote.loadConfig()
        syncDirs = [sync['local'] for sync in content]
        syncDirs.remove('')

        return syncDirs


    def id(self) -> str:
        return self.mac.replace(':', '')


    def retrieveCharacteristics(self) -> tuple[str, str, str, str, str]:
        os = self.execute('uname')
        name = self.execute('hostname')
        if os == 'Windows_NT':
            mac = self.execute('python -c "import uuid, re; print(chr(58).join(re.findall(2*chr(46), hex(uuid.getnode())[2:])))"')
            user = self.execute('echo %USERNAME%')
            ip = self.execute('python -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect((chr(46).join([str(8)]*4), 80)); print(s.getsockname()[0]); s.close()"')
        elif os == 'Linux':
            mac = self.execute('python3 -c "import uuid, re; print(chr(58).join(re.findall(2*chr(46), hex(uuid.getnode())[2:])))"')
            user = self.execute('whoami')
            ip = self.execute('python3 -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect((chr(46).join([str(8)]*4), 80)); print(s.getsockname()[0]); s.close()"')
        else:
            input(f'[5] Error, not a valid operating system for {name}')
            raise SystemExit()
        
        return (mac, user, name, ip, os)


class SSHDevice(Host):
    def __init__(self, mac:str, user:str, name:str, ip:str, os:str):
        self.changes = dict()

        self.mac = mac
        self.user = user
        self.name = name
        self.ip = ip
        self.os = os

        hostMac = hex(uuid.getnode())[2:]
        self.secretKey = pathlib.Path(pathlib.Path.home(), '.ssh', f'{hostMac}_SSH_MediaMove')
        self.publicKey = pathlib.Path(str(self.secretKey)+'.pub')
        if not self.secretKey.exists() or not self.publicKey.exists():
            self.secretKey.parent.mkdir(exist_ok=True)
            subprocess.run(f'ssh-keygen -f {self.secretKey.name} -N ""; chmod 0600 {self.secretKey.name}', shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, cwd=str(self.secretKey.parent))
        
        if os == 'Windows_NT':
            home = pathlib.PureWindowsPath('C:/', 'Users', self.user)
        elif os == 'Linux':
            home = pathlib.PosixPath('/home', self.user)
        else:
            input(f'[4] Error, not a valid operating system for {mac}')
            raise SystemExit()

        self.config = home.joinpath(pathlib.Path('.MediaMove', f'{hostMac}_config.json'))
        self.tree = home.joinpath(pathlib.Path('.MediaMove', f'{hostMac}_tree'))
        self.newtree = home.joinpath(pathlib.Path('.MediaMove', f'{hostMac}_newtree'))


    def execute(self, cmd:str, keepLinebreaks:bool=False) -> str:
        out = subprocess.run(f"ssh -i '{self.secretKey}' {self.user}@{self.ip} '{cmd}'", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.PIPE, encoding='utf-8').stdout 
        if not keepLinebreaks:
            out = out.replace('\n', '')
        return out


    def syncDirs(self) -> list:
        content = self.loadConfig()
        syncDirs = [sync['remote'] for sync in content]
        syncDirs.remove('')

        return syncDirs


    def id(self) -> str:
        return self.mac.replace(':', '')


    def connect(self) -> bool:
        out = subprocess.run(f"ssh -i '{self.secretKey}' {self.user}@{self.ip} 'exit'", shell=True, stderr=subprocess.PIPE, encoding='utf-8').stderr

        if out != '':
            return False

        return True


    def disconnect(self):
        pass


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

        if '' != self.execute(f'ls "{self.config.parent}" 3>&2 2>&1 1>&3'):
            self.execute(f'mkdir "{self.config.parent}"')
        
        if '' != self.execute(f'ls "{self.config}" 3>&2 2>&1 1>&3'):
            content = list()
        else:
            content = json.loads(self.execute(f'cat "{self.config}"'))

        if template not in content:
            content.append(template)
        
            tmpFile = pathlib.Path('.tmp', 'tmp').absolute()
            tmpFile.write_text(json.dumps(content, indent=4))
            subprocess.run(f"scp -q -i '{self.secretKey}' '{str(tmpFile)}' {self.user}@{self.ip}:'{self.config.as_posix()}'", shell=True, stdout=subprocess.DEVNULL)
            tmpFile.unlink()
        
        return content
    

class ADBDevice(Device):
    def __init__(self):
        self.changes = dict()

        self.wired = None
        self.serialno = ''
        self.ip = ''

        self.wireless = None

        hostMac = hex(uuid.getnode())[2:]
        stem = pathlib.Path('/sdcard', '.MediaMove')
        self.config = stem.joinpath(pathlib.Path(f'{hostMac}_config.json'))
        self.tree = stem.joinpath(pathlib.Path(f'{hostMac}_tree'))
        self.newtree = stem.joinpath(pathlib.Path(f'{hostMac}_newtree'))
    

    def execute(self, cmd:str) -> str:
        return self(wake=True).shell(cmd) # TODO: avoid waking up device every time 
    

    def syncDirs(self) -> list:
        content = self.loadConfig()
        syncDirs = [sync['remote'] for sync in content]
        syncDirs.remove('')

        return syncDirs


    def id(self) -> str:
        return self.serialno
    

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
            device.connect(rsa_keys=[signer])
            if '5555\n' != device.shell('getprop service.adb.tcp.port'):
                device.close()
                subprocess.run('adb disconnect && adb tcpip 5555 && adb kill-server && echo done', shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                time.sleep(5)
                device = AdbDeviceUsb()
                device.connect(rsa_keys=[signer], auth_timeout_s=0.1)
        
        except Exception as err:
            if type(err).__name__ in ['UsbDeviceNotFoundError', 'USBErrorNoDevice']:
                pass
            elif type(err).__name__ == 'USBErrorBusy':
                print("[3] Warning, exception occurred:", type(err).__name__, "–", err)
            elif type(err).__name__ == 'UsbReadFailedError':
                device.close()
                input('The fingerprint was not accepted in time. If you trust this machine you can do the following to accept it:\n1. Unlock the device connected to this machine.\n2. Cancel the old fingerprint request displayed on the device.\n3. In the upcoming fingerprint request tick the box to always accept fingerprints from this device and press permit within 10 seconds.\n4. The next fingerprint request will be sent after you press Enter in this script.')
                self.connectWired(signer)
            else:
                if not retry:
                    subprocess.run('adb kill-server', shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
                    time.sleep(5)
                    self.connectWired(signer, retry=True)
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
        
        if '' != self().shell(f'ls {self.config.parent} 3>&2 2>&1 1>&3'):
            self().shell(f'mkdir {self.config.parent}')
        
        if '' != self().shell(f'ls {self.config.parent} 3>&2 2>&1 1>&3'):
            content = list()
        else:
            content = json.loads(self().shell(f'cat {self.config}'))

        if template not in content:
            content.append(template)
        
            buffer = io.BytesIO(bytes(json.dumps(content, indent=4), 'utf-8'))
            self().push(buffer, self.config)
        
        return content