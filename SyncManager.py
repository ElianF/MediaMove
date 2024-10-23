from Device import Host, Device


class SyncManager:
    def __init__(self, remote:Device):
        self.host = Host(remote)
        self.remote = remote

    def getChanges(self):
        self.host.getChanges()
        self.remote.getChanges()