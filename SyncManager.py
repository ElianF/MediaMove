from Device import Host, Device


class SyncManager:
    def __init__(self, device:Device):
        self.host = Host(device)
        self.device = device

    def getChanges(self):
        self.host.getChanges()
        self.device.getChanges()