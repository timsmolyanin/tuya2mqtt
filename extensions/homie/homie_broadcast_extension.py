from __future__ import annotations

import logging
from extensions.base_extension_api import Extension
from core.mqtt_client_wrapper import MqttModule
from core.device_repository import DeviceStore
from extensions.homie.lifecycle.homie_lifecycle_extension import Extension as HomieLifecycleExtension


class HomieBroadcastExtension(Extension):
    """Simple helper reacting on ``homie/5/$broadcast/switch_led`` messages.

    When payload is ``"true"`` or ``"false"`` it propagates the state to all
    devices managed by :class:`HomieLifecycleExtension` that expose a
    ``switch_led`` property.
    """

    def __init__(
        self,
        mqtt: MqttModule,
        device_store: DeviceStore,
        lifecycle: HomieLifecycleExtension | None,
        logger: logging.Logger | None = None,
    ):
        self._mqtt = mqtt
        self._store = device_store
        self._lifecycle = lifecycle
        self._logger = logger or logging.getLogger("HomieBroadcast")

        # Subscribe to broadcast topic
        topic = "homie/5/$broadcast/switch_led"
        self._mqtt.update_topic_handlers({topic: self._on_broadcast})

    # ------------------------------------------------------------------
    # MQTT callback                                                     
    # ------------------------------------------------------------------
    def _on_broadcast(self, topic: str, payload: str) -> None:
        if not self._lifecycle:
            return

        val = payload.strip().lower()
        if val not in ("true", "false"):
            self._logger.debug(
                f"Ignoring unexpected broadcast payload '{payload}'"
            )
            return

        # Iterate through devices known to the store and operate on their bridges
        for dev_id in self._store.get_devices().keys():
            bridge = self._lifecycle.device_bridges.get(dev_id)
            if not bridge:
                continue
            if "switch_led" not in getattr(bridge, "_prop_to_dp", {}):
                continue
            node_id = getattr(bridge, "_prop_to_node", {}).get("switch_led", "relay")
            # Reuse existing on_set helper which converts value and sends to Tuya
            bridge.on_set(node_id, "switch_led", val)
