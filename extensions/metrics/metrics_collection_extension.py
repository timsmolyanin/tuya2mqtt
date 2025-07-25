from __future__ import annotations
import json
from collections import defaultdict
from dataclasses import dataclass, field
from extensions.base_extension_api import SyncExtension, StatusPolled

@dataclass
class PollingMetrics:
    total: int = 0
    errors: dict = field(default_factory=lambda: defaultdict(int))
    slow: int = 0

class Extension(SyncExtension):
    def __init__(self):
        self.metrics = PollingMetrics()

    def on_status(self, event: StatusPolled):
        self.metrics.total += 1
        if event.dps.get("request_status_time", 0) > 5:
            self.metrics.slow += 1

    def on_bridge_stop(self, bridge):
        snapshot = json.dumps({
            "total_polls": self.metrics.total,
            "error_stats": dict(self.metrics.errors),
            "slow_responses": self.metrics.slow,
        })
        bridge._mqtt.mqtt_publish_value_to_topic(
            f"{bridge.service_id}/bridge/metrics", snapshot
        )
    def inc_total(self):
        self.metrics.total += 1
    def inc_slow(self):
        self.metrics.slow += 1
    def record_error(self, err_type: str):
        self.metrics.errors[err_type] += 1
