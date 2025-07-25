from abc import ABC, abstractmethod


class ICloudClient(ABC):
    """Минимум, который сейчас нужен Tuya2MQTT."""
    @abstractmethod
    def getdevices(self, *a, **kw): ...
