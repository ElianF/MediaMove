import os
import pathlib

from adb_shell.auth.sign_pythonrsa import PythonRSASigner
from adb_shell.auth.keygen import keygen

from Device import Device


class DeviceManager:
    def __init__(self):
        self.signer = self.loadKeys()

        self.devices = {
            'usb': self.connectUSBDevice(),
            'wireless': self.connectWifiDevices()
        }


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


    def connectUSBDevice(self) -> Device:
        dev = Device()
        dev.connectWired(self.signer)

        return dev
        

    def connectWifiDevices(self) -> list[Device]:
        return list()



def main():
    deviceManager = DeviceManager()
    pass


if __name__ == '__main__':
    main()