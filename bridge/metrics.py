import time
import json
import threading
from collections import defaultdict
from dataclasses import dataclass, field

import const
from mqtt_module import MqttModule


@dataclass
class PollingMetrics:
    total: int = 0
    errors: dict = field(default_factory=lambda: defaultdict(int))
    slow: int = 0            # >5


class MetricsPublisher:
    """Периодически публикует метрики в MQTT."""

    def __init__(
        self,
        mqtt: MqttModule,
        shutdown_event: threading.Event,
        logger,
        interval: int = 5,
    ):
        self._mqtt = mqtt
        self._shutdown_event = shutdown_event
        self._logger = logger
        self._interval = interval

        self.metrics = PollingMetrics()
        self._lock = threading.Lock()

    def inc_total(self):
        with self._lock:
            self.metrics.total += 1

    def inc_slow(self):
        with self._lock:
            self.metrics.slow += 1

    def record_error(self, err_type: str):
        with self._lock:
            self.metrics.errors[err_type] += 1

    def start(self):
        th = threading.Thread(target=self._loop, name="metrics", daemon=True)
        th.start()

    def _loop(self):
        while not self._shutdown_event.is_set():
            time.sleep(self._interval)
            self._publish()

    def _publish(self):
        with self._lock:
            snapshot = {
                "total_polls": self.metrics.total,
                "error_stats": dict(self.metrics.errors),
                "slow_responses": self.metrics.slow,
            }
        self._mqtt.mqtt_publish_value_to_topic(
            f"{const.SERVICE_ID}/bridge/metrics",
            json.dumps(snapshot),
        )
