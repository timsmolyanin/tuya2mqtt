from __future__ import annotations
from dataclasses import dataclass
import abc, queue, threading

@dataclass
class StatusPolled:
    dev_id: str
    dps: dict

@dataclass
class MqttCommand:
    topic: str
    payload: str

class Extension(abc.ABC):
    def on_bridge_start(self, bridge):
        pass
    def on_bridge_stop(self, bridge):
        pass

class SyncExtension(Extension):
    HOOK_DEADLINE = 0.05
    def on_status(self, event: StatusPolled):
        pass
    def on_command(self, event: MqttCommand):
        pass

class AsyncExtension(Extension):
    _SENTINEL = object()
    def __init__(self):
        self._queue = queue.Queue(maxsize=1000)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._running = False

    def push(self, event):
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            pass

    def on_bridge_start(self, bridge):
        self.bridge = bridge
        self._running = True
        self._thread.start()

    def on_bridge_stop(self, bridge):
        self._running = False
        self._queue.put(self._SENTINEL)
        self._thread.join(timeout=2)

    @abc.abstractmethod
    def handle(self, event):
        pass

    def _loop(self):
        while True:
            ev = self._queue.get()
            if ev is self._SENTINEL or not self._running:
                break
            try:
                self.handle(ev)
            except Exception as exc:
                print(f"[{self.__class__.__name__}] error: {exc}")
