import json
import pathlib
import subprocess
import re
from typing import Iterator

from adb_shell.auth.sign_pythonrsa import PythonRSASigner
from adb_shell.auth.keygen import keygen
import netifaces

from Device import Device


class DeviceManager:
    def __init__(self):
        self.gatewayIP = netifaces.gateways()['default'][netifaces.AF_INET][0]
        proc = subprocess.run('ip neigh show', shell=True, stdout=subprocess.PIPE)
        self.gatewayMac = re.findall(str(self.gatewayIP) + '(?: .*?){3} (.*?) .*', str(proc.stdout))[0]

        self.deviceLog = pathlib.Path('deviceLog.json')
        if not self.deviceLog.exists():
            self.deviceLog.write_text('{}')
        
        self.signer = None
        self.devices:list[Device] = list()


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
        for dev in [self.connectWiredDevice()] + list(self.connectWirelessDevices()):
            if dev != None:
                self.devices.append(dev)


    def connectWiredDevice(self) -> Device:
        dev = Device()
        dev.connectWired(self.signer)

        if dev.wired == None:
            return None

        if dev.ip != None:
            dev.connectWireless(self.signer, dev.ip)

            deviceLogJson = json.loads(self.deviceLog.read_bytes())
            deviceLogJson.setdefault(dev.gatewayMac, dict())[self.serialno] = dev.ip
            self.deviceLog.write_text(json.dumps(deviceLogJson, indent=4))

        return dev
        

    def connectWirelessDevices(self) -> Iterator[Device]:
        deviceLogJson = json.loads(self.deviceLog.read_bytes())

        for serialno, ip in deviceLogJson[self.gatewayMac].items():
            dev = Device()
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
        print(dev.getChanges())
        dev.saveConfig()
    
    deviceManager.disconnect()


if __name__ == '__main__':
    main()