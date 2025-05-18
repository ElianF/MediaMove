import json
import pathlib
import subprocess
import re
from typing import Iterator
import uuid

from adb_shell.auth.sign_pythonrsa import PythonRSASigner
from adb_shell.auth.keygen import keygen
import netifaces

from Device import SSHDevice, ADBDevice
from SyncManager import SyncManager


class DeviceManager:
    def __init__(self):
        self.gatewayIP = netifaces.gateways()['default'][netifaces.AF_INET][0]
        out = subprocess.run('ip neigh show', shell=True, stdout=subprocess.PIPE, encoding='utf-8').stdout
        self.gatewayMac = re.findall(str(self.gatewayIP) + '(?: .*?){3} (.*?) .*', out)[0]

        self.deviceLog = pathlib.Path('deviceLog.json')
        if not self.deviceLog.exists():
            self.deviceLog.write_text('{}')
        
        self.signer = None
        self.devices:list[ADBDevice] = list()


    def loadKeys(self):
        mac = hex(uuid.getnode())[2:]
        secretKey = pathlib.Path(pathlib.Path.home(), '.ssh', f'{mac}_ADB_MediaMove')
        publicKey = pathlib.Path(str(secretKey)+'.pub')

        if not secretKey.exists():
            secretKey.parent.mkdir(exist_ok=True)
            keygen(str(secretKey))
        
        self.signer = PythonRSASigner(
            publicKey.read_text(), 
            secretKey.read_text()
        )


    def connect(self):
        # deviceLogJson = json.loads(self.deviceLog.read_bytes())
        # if self.gatewayMac not in deviceLogJson:
        #     deviceLogJson[self.gatewayMac] = {
        #         'ADB': dict(),
        #         'SSH': dict()
        #     }
        #     self.deviceLog.write_text(json.dumps(deviceLogJson, indent=4))
        
        # device = self.connectWiredADBDevice()
        # if device != None:
        #     self.devices.append(device)
        #     self.devices.extend(self.connectWirelessADBDevices(device.serialno))
        # else:
        #     self.devices.extend(self.connectWirelessADBDevices())
        self.devices.extend(self.connectWirelessSSHDevices())


    def connectWiredADBDevice(self) -> ADBDevice:
        device = ADBDevice()
        device.connectWired(self.signer)

        if device.wired == None:
            return None

        if device.ip != None:
            device.connectWireless(self.signer, device.ip)

            deviceLogJson = json.loads(self.deviceLog.read_bytes())
            if device.serialno not in deviceLogJson[self.gatewayMac]['ADB'] or device.ip != deviceLogJson[self.gatewayMac]['ADB'][device.serialno]:
                deviceLogJson.setdefault(self.gatewayMac, dict())[device.serialno] = device.ip
                self.deviceLog.write_text(json.dumps(deviceLogJson, indent=4))
                

        return device
        

    def connectWirelessADBDevices(self, usbSerialno:str='') -> Iterator[ADBDevice]:
        deviceLogJson = json.loads(self.deviceLog.read_bytes())

        for serialno, ip in deviceLogJson[self.gatewayMac]['ADB'].items():
            if serialno == usbSerialno:
                continue
            device = ADBDevice()
            device.connectWireless(self.signer, ip)
            if serialno == device.serialno:
                yield device


    def connectWirelessSSHDevices(self) -> Iterator[SSHDevice]:
        # TODO: add extra script to add ssh-devices
        deviceLogJson = json.loads(self.deviceLog.read_bytes())

        for mac, d in deviceLogJson[self.gatewayMac]['SSH'].items():
            user, name, ip, os = [(d[key] if key in d else '') for key in ['user', 'name', 'ip', 'os']]
            device = SSHDevice(mac=mac, user=user, name=name, ip=ip, os=os)
            if device.connect():
                characteristics = device.retrieveCharacteristics()
                
                if characteristics != (device.mac, device.user, device.name, device.ip, device.os):
                    del deviceLogJson[self.gatewayMac]['SSH'][device.mac]
                    device.mac, device.user, device.name, device.ip, device.os = characteristics
                    deviceLogJson[self.gatewayMac]['SSH'][device.mac] = {
                        "user": device.user,
                        "name": device.name,
                        "ip": device.ip,
                        "os": device.os
                    }
                    deviceLogJson.write_text(json.dumps(deviceLogJson, indent=4))
                
                yield device


    def disconnect(self):
        for device in self.devices:
            device.disconnect()



def main():
    pathlib.Path('.tmp').mkdir(exist_ok=True)
    
    deviceManager = DeviceManager()
    deviceManager.loadKeys()
    deviceManager.connect()

    for device in deviceManager.devices:
        syncManager = SyncManager(remote=device)
        syncManager.getChanges()
        pass
    
    deviceManager.disconnect()


if __name__ == '__main__':
    main()