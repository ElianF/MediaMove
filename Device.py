from adb_shell.adb_device import AdbDeviceTcp, AdbDeviceUsb

class Device:
    def __init__(self):
        self.wired = None
        self.serialno = None

        self.wireless = None

    
    def connectWired(self, signer):
        try:
            dev = AdbDeviceUsb()
            dev.connect(rsa_keys=[signer], auth_timeout_s=0.1)
        except Exception as e:
            print(e)
            self.wired = None
        else:
            self.wired = dev
            self.serialno = dev.shell('getprop ro.boot.serialno').replace('\n', '')
        


    def connectWireless(self):
        pass