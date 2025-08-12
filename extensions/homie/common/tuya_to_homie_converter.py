
from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

# ---------------------------------------------------------------------------
# 1.  Module‑level utils
# ---------------------------------------------------------------------------

_ALLOWED_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789-"

_IMPORTANT_KEYS = {
    "name", "id", "key", "mac", "uuid", "sn", "category", "product_name",
    "product_id", "biz_type", "model", "sub", "icon", "ip", "version"
}


def _sanitize_id(raw: str | int) -> str:
    """Make a string safe for Homie (lowercase [a‑z0‑9‑])."""
    raw = str(raw).lower()
    out = "".join(c if c in _ALLOWED_CHARS else "-" for c in raw)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "id"


def _tuya_extension(dev: Dict[str, Any]) -> Dict[str, Any]:
    """Return filtered Tuya metadata for extensions.tuya."""
    return {k: v for k, v in dev.items() if k in _IMPORTANT_KEYS}

# ---------------------------------------------------------------------------
# 2.  Template infrastructure
# ---------------------------------------------------------------------------

class TemplateManager:
    """Load JSON templates from *template_dir* and provide match lookup."""

    def __init__(self, template_dir: str | Path):
        self._dir = Path(template_dir)
        self._templates: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self._dir.exists():
            return
        for f in self._dir.glob("*.json"):
            try:
                self._templates.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception as exc:
                print(f"[TemplateManager] Failed to load {f}: {exc}")

    def find_template(self, device: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for tpl in self._templates:
            cond = tpl.get("match", {})
            if all(str(device.get(k)) == str(v) for k, v in cond.items()):
                return tpl.get("homie")
        return None

# ---------------------------------------------------------------------------
# 3.  Heuristic fallback converter
# ---------------------------------------------------------------------------

class GenericConverter:
    """Guess‑based Tuya → Homie mapper."""

    _ALIAS: List[Tuple[re.Pattern, str]] = [
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

    _NODE: List[Tuple[str, re.Pattern]] = [
        ("relay", re.compile(r"^(on|switch)$", re.I)),
        ("light", re.compile(r"switch_led|bright|color|colour|work_mode|scene|flash|temp", re.I)),
        ("meter", re.compile(r"^(current|power|voltage|energy|cur_)", re.I)),
        ("timer", re.compile(r"countdown|timer", re.I)),
    ]

    _EXCLUDE: List[re.Pattern] = [
        re.compile(r"flash_scene_\d+", re.I),
        re.compile(r"scene_data(_v2)?", re.I),
        re.compile(r"music_data", re.I),
        re.compile(r"control_data", re.I),
        re.compile(r"countdown", re.I),
    ]

    # helpers -------------------------------------------------------------

    @classmethod
    def _alias(cls, code: str) -> Optional[str]:
        for pat, alias in cls._ALIAS:
            if pat.search(code):
                return alias
        return None

    @classmethod
    def _is_excluded(cls, code: str) -> bool:
        return any(p.search(code) for p in cls._EXCLUDE)

    @classmethod
    def _node_id(cls, code: str) -> Optional[str]:
        for nid, pat in cls._NODE:
            if pat.search(code):
                return nid
        return None

    @staticmethod
    def _integer_format(values: Dict[str, Any]) -> Optional[str]:
        if not values:
            return None
        parts = [str(values.get("min", "")), str(values.get("max", ""))]
        step = values.get("step")
        if step not in (None, 0):
            parts.append(str(step))
        fmt = ":".join(parts).rstrip(":")
        return fmt if fmt and fmt != ":" else None

    @staticmethod
    def _enum_format(values: Dict[str, Any]) -> Optional[str]:
        rng = values.get("range")
        return ",".join(rng) if isinstance(rng, list) and rng else None

    @classmethod
    def _datatype(cls, dp: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        typ = dp.get("type")
        vals = dp.get("values", {})
        if typ == "Boolean":
            return "boolean", None
        if typ == "Integer":
            return "integer", cls._integer_format(vals)
        if typ == "Enum":
            return "enum", cls._enum_format(vals)
        if typ == "Json":
            if re.search(r"colou?r", dp.get("code", ""), re.I):
                return "color", "hsv"
            return "json", None
        return "string", None

    @classmethod
    def _property(cls, dp: Dict[str, Any]) -> Dict[str, Any]:
        datatype, fmt = cls._datatype(dp)
        prop: Dict[str, Any] = {
            "datatype": datatype,
            "settable": not dp.get("code", "").lower().startswith("cur_"),
            "retained": True,
        }
        if fmt:
            prop["format"] = fmt
        unit = dp.get("values", {}).get("unit")
        if unit:
            prop["unit"] = unit
        alias = cls._alias(dp.get("code", ""))
        prop["name"] = alias.replace("_", " ").title() if alias else (dp.get("code") or "").replace("_", " ").title()
        return prop

    # public --------------------------------------------------------------

    def device_to_homie(self, dev: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
                
        dev_id = _sanitize_id(dev.get("friendly_name") or dev.get("id") or dev.get("uuid") or dev.get("mac") or "device") or dev.get("uuid") or dev.get("mac") or "device"


        name = dev.get("name") or dev.get("product_name") or dev_id
        nodes: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"properties": {}})

        for dp in (dev.get("mapping") or {}).values():
            code = dp.get("code")
            if not code or self._is_excluded(code):
                continue
            node_id = self._node_id(code)
            if node_id is None:
                continue
            props = nodes[node_id]["properties"]
            pid = self._alias(code) or _sanitize_id(code)
            if pid in props:
                i = 2
                while f"{pid}-{i}" in props:
                    i += 1
                pid = f"{pid}-{i}"
            props[pid] = self._property(dp)

        for nid, n in nodes.items():
            n.setdefault("name", nid.title())

        return dev_id, {
            "homie": "5.0",
            "version": int(time.time()),
            "name": name,
            "nodes": dict(nodes),
            "extensions": {"tuya": _tuya_extension(dev)},
        }

    def devices_to_homie(self, devices: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {d: desc for d, desc in map(self.device_to_homie, devices)}

# ---------------------------------------------------------------------------
# 4.  Orchestrator
# ---------------------------------------------------------------------------

@dataclass
class TuyaHomieConverter:
    template_manager: TemplateManager
    generic_converter: GenericConverter = field(default_factory=GenericConverter)

    def convert_device(
        self, device: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any], Dict[Tuple[str, str], str] | None, bool]:
        tpl = self.template_manager.find_template(device)
        if tpl:
            return self._apply_template(device, tpl)
        dev_id, desc = self.generic_converter.device_to_homie(device)
        return dev_id, desc, None, False

    def convert_devices(self, devices: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {d: desc for d, desc, _, _ in map(self.convert_device, devices)}

    # internal
    def _apply_template(
        self, device: Dict[str, Any], tpl: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any], Dict[Tuple[str, str], str], bool]:
        dev_id = _sanitize_id(
            device.get("id") or device.get("uuid") or device.get("mac") or "device"
        )
        name = device.get("name") or device.get("product_name") or dev_id
        desc = json.loads(json.dumps(tpl))  # deep copy

        mapping: Dict[Tuple[str, str], str] = {}
        for node_id, node in desc.get("nodes", {}).items():
            for prop_id, p in node.get("properties", {}).items():
                dp = p.pop("dp", None)
                if dp is not None:
                    mapping[(node_id, prop_id)] = str(dp)

        desc.setdefault("homie", "5.0")
        desc.setdefault("version", int(time.time()))
        desc.setdefault("name", name)
        desc.setdefault("extensions", {})["tuya"] = _tuya_extension(device)
        return dev_id, desc, mapping, True