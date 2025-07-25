from __future__ import annotations
import json
from collections import defaultdict
from dataclasses import dataclass, field
import time
import queue
from extensions.base_extension_api import AsyncExtension, StatusPolled

@dataclass
class PollingMetrics:
    total: int = 0
    errors: dict = field(default_factory=lambda: defaultdict(int))
    slow: int = 0

class Extension(AsyncExtension):
    def __init__(self, publish_interval: float = 30.0):
        super().__init__()
        self.metrics = PollingMetrics()
        self._publish_interval = publish_interval
        self._last_publish = time.time()

    def _publish_snapshot(self):
        if not hasattr(self, "bridge"):
            return
        snapshot = json.dumps({
            "total_polls": self.metrics.total,
            "error_stats": dict(self.metrics.errors),
            "slow_responses": self.metrics.slow,
        })
        self.bridge._mqtt.mqtt_publish_value_to_topic(
            f"{self.bridge.service_id}/bridge/metrics", snapshot
        )

    def handle(self, event):
        etype, data = event
        if etype == "inc_total":
            self.metrics.total += 1
        elif etype == "inc_slow":
            self.metrics.slow += 1
        elif etype == "error":
            self.metrics.errors[data] += 1
        elif etype == "status":
            self.metrics.total += 1
            if data.get("request_status_time", 0) > 5:
                self.metrics.slow += 1

        now = time.time()
        if now - self._last_publish >= self._publish_interval:
            self._last_publish = now
            self._publish_snapshot()

    def _loop(self):
        while True:
            try:
                ev = self._queue.get(timeout=self._publish_interval)
            except queue.Empty:
                ev = None
            if ev is self._SENTINEL or not self._running:
                break
            if ev is not None:
                try:
                    self.handle(ev)
                except Exception as exc:
                    print(f"[{self.__class__.__name__}] error: {exc}")
            else:
                # timeout - publish snapshot even if no new events
                self._publish_snapshot()

    def on_bridge_stop(self, bridge):
        super().on_bridge_stop(bridge)
        self._publish_snapshot()

    def inc_total(self):
        self.push(("inc_total", None))

    def inc_slow(self):
        self.push(("inc_slow", None))

    def record_error(self, err_type: str):
        self.push(("error", err_type))

    def on_status(self, event: StatusPolled):
        self.push(("status", event.dps))
