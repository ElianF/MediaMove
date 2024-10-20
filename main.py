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
        self.host = lambda dev: Host(dev)


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
        dev = self.connectWiredDevice()
        if dev != None:
            self.devices.append(dev)
            self.devices.extend(self.connectWirelessDevices(dev.serialno))
        else:
            self.devices.extend(self.connectWirelessDevices())


    def connectWiredDevice(self) -> PortableDevice:
        dev = PortableDevice()
        dev.connectWired(self.signer)

        if dev.wired == None:
            return None

        if dev.ip != None:
            dev.connectWireless(self.signer, dev.ip)

            deviceLogJson = json.loads(self.deviceLog.read_bytes())
            deviceLogJson.setdefault(self.gatewayMac, dict())[dev.serialno] = dev.ip
            self.deviceLog.write_text(json.dumps(deviceLogJson, indent=4))

        return dev
        

    def connectWirelessDevices(self, usbSerialno:str='') -> Iterator[PortableDevice]:
        deviceLogJson = json.loads(self.deviceLog.read_bytes())

        for serialno, ip in deviceLogJson[self.gatewayMac].items():
            if serialno == usbSerialno:
                continue
            dev = PortableDevice()
            dev.connectWireless(self.signer, ip)
            if serialno == dev.serialno:
                yield dev


    def disconnect(self):
        for dev in self.devices:
            dev.disconnect()



def main():
    pathlib.Path('.tmp').mkdir(exist_ok=True)
    
    deviceManager = DeviceManager()
    deviceManager.loadKeys()
    deviceManager.connect()

    for dev in deviceManager.devices:
        dev.loadConfig()

        syncManager = SyncManager(src=dev, dst=deviceManager.host(dev))
        syncManager.getChanges()
        
        dev.saveConfig()
    
    deviceManager.disconnect()


if __name__ == '__main__':
    main()