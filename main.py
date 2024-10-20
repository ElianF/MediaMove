import json
import pathlib
import subprocess
import re
from typing import Iterator

from adb_shell.auth.sign_pythonrsa import PythonRSASigner
from adb_shell.auth.keygen import keygen
import netifaces

from Device import Host, StationaryDevice, PortableDevice
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
        self.devices:list[PortableDevice] = list()


    def loadKeys(self):
        secretKey = pathlib.Path('.key', 'adbkey')
        publicKey = pathlib.Path('.key', 'adbkey.pub')

        if not secretKey.exists():
            secretKey.parent.mkdir(exist_ok=True)
            keygen(str(secretKey))
        
        self.signer = PythonRSASigner(
            publicKey.read_text(), 
            secretKey.read_text()
        )


    def connect(self):
        device = self.connectWiredDevice()
        if device != None:
            self.devices.append(device)
            self.devices.extend(self.connectWirelessDevices(device.serialno))
        else:
            self.devices.extend(self.connectWirelessDevices())


    def connectWiredDevice(self) -> PortableDevice:
        device = PortableDevice()
        device.connectWired(self.signer)

        if device.wired == None:
            return None

        if device.ip != None:
            device.connectWireless(self.signer, device.ip)

            deviceLogJson = json.loads(self.deviceLog.read_bytes())
            deviceLogJson.setdefault(self.gatewayMac, dict())[device.serialno] = device.ip
            self.deviceLog.write_text(json.dumps(deviceLogJson, indent=4))

        return device
        

    def connectWirelessDevices(self, usbSerialno:str='') -> Iterator[PortableDevice]:
        deviceLogJson = json.loads(self.deviceLog.read_bytes())

        for serialno, ip in deviceLogJson[self.gatewayMac].items():
            if serialno == usbSerialno:
                continue
            device = PortableDevice()
            device.connectWireless(self.signer, ip)
            if serialno == device.serialno:
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
        syncManager = SyncManager(device=device)
        syncManager.getChanges()
    
    deviceManager.disconnect()


if __name__ == '__main__':
    main()