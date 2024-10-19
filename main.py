import json
import pathlib
import subprocess
import re

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
        
        self.signer = self.loadKeys()
        self.devices = self.connect()


    def loadKeys(self):
        secretKey = pathlib.Path('.key', 'adbkey')
        publicKey = pathlib.Path('.key', 'adbkey.pub')

        if not secretKey.exists():
            secretKey.parent.mkdir(exist_ok=True)
            keygen(str(secretKey))
        
        signer = PythonRSASigner(
            publicKey.read_text(), 
            secretKey.read_text()
        )

        return signer


    def connect(self) -> list[Device]:
        return [self.connectWiredDevice()] + self.connectWirelessDevices()


    def connectWiredDevice(self) -> Device:
        dev = Device()
        dev.connectWired(self.signer)
        if dev.ip != None:
            dev.connectWireless(self.signer, dev.ip)

            deviceLogJson = json.loads(self.deviceLog.read_bytes())
            deviceLogJson.setdefault(dev.serialno, dict())[self.gatewayMac] = dev.ip
            self.deviceLog.write_text(json.dumps(deviceLogJson, indent=4))

        return dev
        

    def connectWirelessDevices(self) -> list[Device]:
        return list()


    def disconnect(self):
        for dev in self.devices:
            dev.disconnect()



def main():
    deviceManager = DeviceManager()
    pass
    deviceManager.disconnect()


if __name__ == '__main__':
    main()