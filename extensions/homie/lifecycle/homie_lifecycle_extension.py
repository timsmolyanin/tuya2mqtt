
"""HomieSyncManager – the glue‑layer that keeps *TuyaDevice* objects,
their *HomieDevice* twins and the device_store in sync:

* devices added via old bridge API   → new HomieDevice is created
* devices removed via old API       → HomieDevice is torn down
* empty retained payload on …/$state (Homie way) → TuyaDevice removed
* friendly‑name change              → optional Homie *device‑ID* rename
* key update                        → \$description re‑published
"""
from __future__ import annotations

import json
from extensions.base_extension_api import SyncExtension
import logging
from typing import Dict, Any

from core.mqtt_client_wrapper import MqttModule
from extensions.homie.common.homie_device_model import HomieDevice
from extensions.homie.common.homie_bridge_adapter import DeviceBridge
from extensions.homie.common.tuya_to_homie_converter import TuyaHomieConverter, _sanitize_id
from core.device_repository import DeviceStore
from core.tuya import tuya_constants as const


class Extension(SyncExtension):
    def __init__(
        self,
        mqtt: MqttModule,
        device_store: DeviceStore,
        converter: TuyaHomieConverter,
        logger: logging.Logger | None = None,
    ):
        self._mqtt = mqtt
        self._store = device_store
        self._conv = converter
        self._logger = logger or logging.getLogger("HomieSync")
        self.device_bridges: Dict[str, DeviceBridge] = {}

        # create representations for already known devices
        for dev in self._store.get_devices().values():
            self._create_bridge(dev)

        # subscribe to \$state deletions
        topic_pat = "homie/5/+/$state"
        self._mqtt.update_topic_handlers({topic_pat: self._on_homie_state})

    # ------------------------------------------------------------------ #
    # external API                                                       #
    # ------------------------------------------------------------------ #
    def on_devices_added(self, new_devs_conf: list[dict]):
        for dev_conf in new_devs_conf:
            dev_id = dev_conf["id"]
            dev_obj = self._store.get_devices(dev_id)
            if dev_obj:
                self._create_bridge(dev_obj)

    def on_device_removed(self, dev_id: str):
        self._drop_bridge(dev_id)

    def on_device_key_changed(self, dev_id: str):
        br = self.device_bridges.get(dev_id)
        if br:
            # regenerate description
            _, desc, _, _ = self._conv.convert_device(self._store.get_devices(dev_id).to_dict())
            br.homie.update_description(desc)
            self._logger.debug(f"Republished description for {dev_id}")

    def on_device_renamed(self, dev_id: str, new_name: str):
        # remove old Homie‑tree then create new one (Homie‑spec demands new id)
        self._drop_bridge(dev_id)
        self._create_bridge(self._store.get_devices(dev_id))

    # ------------------------------------------------------------------ #
    # internals                                                          #
    # ------------------------------------------------------------------ #
    def _create_bridge(self, tuya_dev):
        try:
            homie_id, desc, mapping, strict = self._conv.convert_device(tuya_dev.to_dict())
            holder = {}
            def _on_set(node, prop, val, _h=holder):
                if 'bridge' in _h:
                    _h['bridge'].on_set(node, prop, val)
            homie = HomieDevice(self._mqtt, homie_id, desc, on_set=_on_set)
            bridge = DeviceBridge(tuya_dev, homie, mapping=mapping, strict=strict, logger=self._logger)
            holder['bridge'] = bridge
            self.device_bridges[tuya_dev.dev_id] = bridge
            self._logger.info(f"Homie device ready: Tuya {tuya_dev.dev_id} → homie/5/{homie_id}")
        except Exception as exc:
            self._logger.error(f"Failed to create Homie bridge for {tuya_dev.dev_id}: {exc}")

    def _drop_bridge(self, dev_id: str):
        br = self.device_bridges.pop(dev_id, None)
        if not br:
            return
        try:
            br.homie.teardown()
        except Exception as exc:
            self._logger.warning(f"Error during teardown of {dev_id}: {exc}")
        self._logger.info(f"Homie device removed for {dev_id}")

    # ------------------------------------------------------------------ #
    # MQTT callbacks                                                     #
    # ------------------------------------------------------------------ #
    def _on_homie_state(self, topic: str, payload: str):
        """Triggered when someone publishes to …/$state. We care only about *empty* retained payloads
        meaning *device removal* per convention."""
        if payload != "":
            return                          # just a state change
        # topic = homie/5/<homie_id>/ $state
        homie_id = topic.split("/")[2]
        # find Tuya dev_id that maps to this homie_id
        for dev_id, br in list(self.device_bridges.items()):
            if br.homie.dev_id == homie_id:
                self._logger.info(f"Received delete for homie/5/{homie_id}")

                # 1. убираем из DeviceStore (если успело появиться)
                try:
                    self._store.remove_device(dev_id)
                except KeyError:
                    pass

                # 2. чистим devices.json
                conf = self._store.read(const.DEVICES_CONF_FILE)
                conf = [d for d in conf if d.get("id") != dev_id]
                self._store.write(const.DEVICES_CONF_FILE, conf)

                # 3. снимаем retained-ветку Homie
                self._drop_bridge(dev_id)
                break
