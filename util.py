import functools
import errno
import socket
from contextlib import closing
from const import BridgeState

def require_state(*allowed):
    def deco(func):
        @functools.wraps(func)
        def wrapper(self, *a, **kw):
            with self._state_lock:
                st = self._state
            if st in allowed:
                return func(self, *a, **kw)
            self._logger.warning(
                f"{func.__name__} skipped - tuya2mqtt bridge current state {st.name}"
            )
            self._publish_bridge_status()
        return wrapper
    return deco


_CHECK_IP:  tuple[str, int]  = ("1.1.1.1", 53) # Cloudflare DNS
_UDP_DUMMY: tuple[str, int]  = ("192.0.2.1", 9)
_TIMEOUT:   float            = 1.0

def _probe_lan() -> bool:
    try:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as s:
            s.connect(_UDP_DUMMY)
            _ = s.getsockname()[0]
        return True
    except OSError:
        return False


def _probe_internet(timeout: float = _TIMEOUT) -> bool:
    try:
        with closing(socket.create_connection(_CHECK_IP, timeout)):
            return True                       # ONLINE
    except OSError as e:
        if e.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH):
            return False                      # No Internet connection
        # Timeout / Connection refused -> No Internet connection
        return False


def _determine_net_state() -> BridgeState:
    if not _probe_lan():
        return BridgeState.OFFLINE
    if _probe_internet():
        return BridgeState.ONLINE
    return BridgeState.LAN_ONLY


if __name__ == '__main__':
    ...
