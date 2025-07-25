
"""Homie 5 – minimal runtime for publishing devices that follow the
convention (\u201chomie/5/...\u201d topics).

It is **not** a full implementation (that is a huge endeavour) but it covers
the core elements required by the spec section *Device / Node / Property
structure*, the *device lifecycle* and basic *command* handling for settable
properties.  Everything else (alerts, logging, broadcast etc.) is exposed as
thin convenience wrappers so that the rest of Tuya2MQTT can call them when
needed.

The module is *self‑contained*: importing it does **not** introduce new
dependencies – it only relies on `mqtt_module.MqttModule`, the very wrapper
already used throughout the project.

Typical usage
-------------

```python
mqtt = MqttModule(...)

device = HomieDevice(
    mqtt=mqtt,
    dev_id="lamp‑kitchen",
    description={
        "homie": "5.0",
        "name": "Kitchen lamp",
        "version": 1,
        "nodes": {
            "light": {
                "name": "Main light",
                "properties": {
                    "power": {"datatype": "boolean", "settable": True},
                    "brightness": {"datatype": "integer", "settable": True, "format": "0:100"}
                }
            }
        }
    },
    on_set=your_callback      # optional – gets (node_id, prop_id, value)
)
```

Once instantiated the object immediately publishes:

1. `homie/5/<dev_id>/$state           = "init"   (QoS2, retained)`
2. `homie/5/<dev_id>/$description     = <JSON>`    (QoS2, retained)
3. subscribes to all `…/<node>/<prop>/set` topics (QoS0, **non‑retained**)
4. and finally flips `$state` from `init` → `ready`

"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict

from mqtt_module import MqttModule


def _topic(device_id: str, *levels: str) -> str:
    return "/".join(["homie", "5", device_id, *levels])


class HomieDevice:
    def __init__(
        self,
        mqtt: MqttModule,
        dev_id: str,
        description: Dict[str, Any],
        on_set: Callable[[str, str, str], Any] | None = None,
        logger: logging.Logger | None = None,
    ):
        self._mqtt = mqtt
        self.dev_id = dev_id
        self.description = description
        self._on_set_cb = on_set
        self._logger = logger or logging.getLogger(f"HomieDevice[{dev_id}]")
        self._base = _topic(dev_id)

        # 1. announce ourselves → init
        self._publish_state("init")
        # 2. publish \$description
        self._mqtt.publish(f"{self._base}/$description", json.dumps(self.description))
        # 3. subscribe to /set for settable props
        self._register_set_handlers()
        # 4. ready!
        self._publish_state("ready")

    # ------------------------------------------------------------------
    # Helpers – publishing
    # ------------------------------------------------------------------
    def _publish_state(self, state: str):
        self._mqtt.publish(f"{self._base}/$state", state)

    def publish_property(self, node_id: str, prop_id: str, value: str | int | float | bool):
        """Publish a regular property value (retained, QoS2)."""
        t = f"{self._base}/{node_id}/{prop_id}"
        self._mqtt.publish(t, value)

    def publish_target(self, node_id: str, prop_id: str, value: str | int | float | bool):
        """Publish \$target helper (retained, QoS2)."""
        t = f"{self._base}/{node_id}/{prop_id}/$target"
        self._mqtt.publish(t, value)

    # Alert / log helpers -------------------------------------------------
    def alert_set(self, alert_id: str, message: str):
        self._mqtt.publish(f"{self._base}/$alert/{alert_id}", message)

    def alert_clear(self, alert_id: str):
        # Zero‑length payload = delete
        self._mqtt.publish(f"{self._base}/$alert/{alert_id}", "", retain=True)

    def log(self, level: str, message: str):
        level = level.lower()
        if level not in ("debug", "info", "warn", "error", "fatal"):
            raise ValueError("Invalid log level")
        # Non‑retained
        self._mqtt.publish(f"{self._base}/$log/{level}", message, retain=False)

    # ------------------------------------------------------------------
    # Internal – subscribe to /set
    # ------------------------------------------------------------------
    def _register_set_handlers(self):
        if not self._on_set_cb:
            return

        nodes: Dict[str, Any] = self.description.get("nodes", {})
        for node_id, node in nodes.items():
            for prop_id, prop in node.get("properties", {}).items():
                if prop.get("settable"):
                    topic_pattern = f"{self._base}/{node_id}/{prop_id}/set"
                    # non‑retained, QoS0 according to spec – our wrapper uses defaults
                    self._mqtt.update_topic_handlers({topic_pattern: self._make_handler(node_id, prop_id)})

    def _make_handler(self, node_id: str, prop_id: str):
        def _handler(topic: str, payload: str):
            self._logger.debug(f"\u2192 SET {topic} = {payload}")
            try:
                if self._on_set_cb:
                    self._on_set_cb(node_id, prop_id, payload)
            except Exception as exc:
                self._logger.error(f"on_set callback raised: {exc}")
        return _handler
    
    def teardown(self):
        """Remove retained topics for full tree (state, description, nodes, props)."""
        # clear $state first
        self._mqtt.publish(f"{self._base}/$state", "", retain=True)
        # clear $description
        self._mqtt.publish(f"{self._base}/$description", "", retain=True)
        nodes = self.description.get("nodes", {})
        for node_id, node in nodes.items():
            # node attributes
            for attr in ("$name", "$type", "$properties"):
                self._mqtt.publish(f"{self._base}/{node_id}/{attr}", "", retain=True)
            # properties
            for prop_id, prop in node.get("properties", {}).items():
                # property attributes
                for attr in (
                    "$name", "$datatype", "$settable", "$unit", "$format", "$target",
                    "$retained"
                ):
                    self._mqtt.publish(f"{self._base}/{node_id}/{prop_id}/{attr}", "", retain=True)
                # property value itself
                self._mqtt.publish(f"{self._base}/{node_id}/{prop_id}", "", retain=True)

    def update_description(self, new_desc: Dict[str, Any]):
        """Publish new $description (+ version bump) while $state=init."""
        self._publish_state("init")
        self.description = new_desc
        self._mqtt.publish(f"{self._base}/$description", json.dumps(self.description))
        self._publish_state("ready")
