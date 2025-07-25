
from __future__ import annotations

import re
import logging
from typing import Any, Dict

from extensions.homie.common.homie_device_model import HomieDevice
from core.tuya_device_entity import TuyaDevice

# ---------------------------------------------------------------------------
# Re‑used patterns from GenericConverter
# ---------------------------------------------------------------------------

_ALIAS = [
    (re.compile(r"switch_led", re.I), "switch_led"),
    (re.compile(r"^(switch)$", re.I), "switch"),
    (re.compile(r"bright", re.I), "brightness"),
    (re.compile(r"colour|color", re.I), "color"),
    (re.compile(r"temp(_value)?", re.I), "temperature"),
    (re.compile(r"cur_current", re.I), "current"),
    (re.compile(r"cur_power", re.I), "power"),
    (re.compile(r"cur_voltage", re.I), "voltage"),
    (re.compile(r"countdown", re.I), "timer"),
    (re.compile(r"work_mode", re.I), "mode"),
]

_ALLOWED_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789-"

def _alias(dp_code: str) -> str | None:
    for rx, alias in _ALIAS:
        if rx.search(dp_code):
            return alias
    return None

def _sanitize(raw: str | int) -> str:
    raw = str(raw).lower()
    out = "".join(c if c in _ALLOWED_CHARS else "-" for c in raw)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "id"

def _property_id(dp_code: str) -> str:
    return _alias(dp_code) or _sanitize(dp_code)

def _node_id(dp_code: str) -> str:
    NODE = [
        ("relay", re.compile(r"^(on|switch)$", re.I)),
        ("light", re.compile(r"switch_led|bright|color|colour|work_mode|scene|flash|temp", re.I)),
        ("meter", re.compile(r"^(current|power|voltage|energy|cur_)", re.I)),
        ("timer", re.compile(r"countdown|timer", re.I)),
    ]
    for nid, rx in NODE:
        if rx.search(dp_code):
            return nid
    return "general"

class DeviceBridge:
    """Glue between *TuyaDevice* and its *HomieDevice* representation."""

    def __init__(self, tuya_dev: TuyaDevice, homie_dev: HomieDevice, logger: logging.Logger | None = None):
        self.tuya = tuya_dev
        self.homie = homie_dev
        self._logger = logger or logging.getLogger(f"DeviceBridge[{tuya_dev.dev_id}]")
        # Build mapping Homie‑prop‑id → (dp_code, node_id)
        self._prop_to_dp: Dict[str, str] = {}
        self._prop_to_node: Dict[str, str] = {}
        for dp_num, mapping in tuya_dev.get_mapping().items():
            dp_code = mapping.get("code", str(dp_num))
            prop_id = _property_id(dp_code)
            node_id = _node_id(dp_code)
            self._prop_to_dp[prop_id] = dp_code
            self._prop_to_node[prop_id] = node_id

    # ------------------------------------------------------------------
    # incoming Tuya → Homie
    # ------------------------------------------------------------------
    def publish_status(self, dps: Dict[str, Any]):
        for dp_code, value in dps.items():
            if dp_code == "request_status_time":
                continue
            prop_id = _property_id(dp_code)
            node_id = self._prop_to_node.get(prop_id) or _node_id(dp_code)
            if isinstance(value, bool):
                value = "true" if value else "false"
            self.homie.publish_property(node_id, prop_id, value)

    # ------------------------------------------------------------------
    # incoming Homie → Tuya
    # ------------------------------------------------------------------
    def on_set(self, node_id: str, prop_id: str, value_raw: str):
        dp_code = self._prop_to_dp.get(prop_id)
        if not dp_code:
            self._logger.warning(f"Unknown property '{prop_id}' for device {self.tuya.dev_id}")
            return
        # Try to parse basic types
        value: Any = value_raw
        if value_raw.lower() in ("true", "false"):
            value = value_raw.lower() == "true"
        else:
            try:
                # int or float fallback
                if "." in value_raw:
                    value = float(value_raw)
                else:
                    value = int(value_raw)
            except ValueError:
                pass  # leave as string
        self._logger.debug(f"Set {dp_code} <- {value}")
        self.tuya.set_status_async({dp_code: value})
        # acknowledge target
        try:
            self.homie.publish_target(node_id, prop_id, value_raw)
        except Exception:
            pass  # not critical
