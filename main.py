import os
import pathlib

from adb_shell.auth.sign_pythonrsa import PythonRSASigner
from adb_shell.auth.keygen import keygen

from Device import Device


class DeviceManager:
    def __init__(self):
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