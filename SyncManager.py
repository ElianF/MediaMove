from Device import PortableDevice


class SyncManager:
    def __init__(self, src:PortableDevice, dst:PortableDevice):
        self.src = src
        self.dst = dst


    def getChanges(self):
        self.src.getChanges()
        self.dst.getChanges()