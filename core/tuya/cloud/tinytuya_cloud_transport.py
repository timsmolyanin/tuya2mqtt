import tinytuya
from .abstract_cloud_transport import ICloudClient


class TinyCloud(ICloudClient):
    def __init__(self, **kw):
        self._cloud = tinytuya.Cloud(**kw)

    def __getattr__(self, item):
        return getattr(self._cloud, item)
    
    def set_device_id(self, devices_ids_list):
        self._cloud.apiDeviceID = devices_ids_list

    def getdevices(self, *a, **kw):
        return self._cloud.getdevices(*a, **kw)

Cloud = TinyCloud
