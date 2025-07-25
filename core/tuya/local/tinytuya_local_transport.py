import tinytuya
from core.tuya import tuya_constants as const
from .abstract_local_transport import ILocalTransport


class TinyLocalTransport(ILocalTransport):
    """
    Адаптер, который оборачивает tinytuya.(Bulb)Device
    и реализует ровно те методы, которые использует TuyaDevice.
    """

    def __init__(
        self, *, dev_id, ip=None, local_key=None,
        category=None,
        version="3.4",
        connection_timeout=5, connection_retry_limit=2,
        connection_retry_delay=1
    ):
        kw = dict(
            dev_id=dev_id,
            address=ip,
            local_key=local_key,
            version=version,
            connection_timeout=connection_timeout,
            connection_retry_limit=connection_retry_limit,
            connection_retry_delay=connection_retry_delay,
        )

        # Светотехника → BulbDevice, остальные — Device
        if category in const.HRF_TUYA_DEVICE_CATEGORY:
            self._dev = tinytuya.BulbDevice(**kw)
        else:
            self._dev = tinytuya.Device(**kw)

        self._dev.set_socketPersistent(False)

    # ---------- методы, требуемые TuyaDevice -----------------
    def status(self):
        return self._dev.status()

    def turn_on(self):
        return self._dev.turn_on()

    def turn_off(self):
        return self._dev.turn_off()

    def set_status(self, on, switch=1):
        return self._dev.set_status(on, switch)

    def set_value(self, dp, value):
        return self._dev.set_value(dp, value)

    # --- делегирование прочих вызовов (brightness, hsv, etc.) --
    def __getattr__(self, item):
        return getattr(self._dev, item)
