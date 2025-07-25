from abc import ABC, abstractmethod

class ILocalTransport(ABC):
    """Abstract local transport for Tuya devices."""

    @abstractmethod
    def status(self):
        raise NotImplementedError

    @abstractmethod
    def turn_on(self):
        raise NotImplementedError

    @abstractmethod
    def turn_off(self):
        raise NotImplementedError

    @abstractmethod
    def set_status(self, *args, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def set_value(self, *args, **kwargs):
        raise NotImplementedError
