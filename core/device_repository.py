import json
import threading
from typing import List, Dict
from core.tuya_device_entity import TuyaDevice
from core.tuya import tuya_constants as const


class DeviceStore:
    """
    Чтение / запись devices.json + полезные утилиты для слияния
    локальной информации со сканом из облака.
    """

    def __init__(self, logger):
        self._logger = logger
        self._lock = threading.RLock()
        self._devices: Dict[str, TuyaDevice] = {}

        self._name_to_id: Dict[str, str] = {}

    def get_devices(self, dev_id: str=None):
        if not dev_id:
            return self._devices
        else:
            device = self._devices.get(dev_id, {})
            return device
    
    def get_devices_friendly_name(self, friendly_name: str=None):
        if not friendly_name:
            return self._name_to_id
        else:
            device_id = self._name_to_id.get(friendly_name, None)
            return device_id
    
    def remove_device(self, dev_id: str):
        del self._devices[dev_id]

    def read(self, path: str) -> list:
        """Read JSON form file, return list or dict of devices or empty list."""
        with self._lock:
            try:
                with open(path, "r") as fh:
                    data = json.load(fh)
                self._logger.info(f"Loaded {len(data)} devices from {path}")
                return data
            except FileNotFoundError:
                self._logger.warning(f"{path} not found.")
                return []
            except Exception as exc:
                self._logger.error(f"Error reading {path}: {exc}")
                return []

    def write(self, path: str, data):
        with self._lock:
            try:
                with open(path, "w") as fh:
                    json.dump(data, fh, indent=4)
                self._logger.info(f"Saved {len(data)} devices to {path}")
            except Exception as exc:
                self._logger.error(f"Error writing {path}: {exc}")
    
    def load_devices(self, conf):
        try:
            cnt_of_devices = 0
            for obj in conf:
                dev = TuyaDevice.from_dict(obj)
                self._devices[dev.dev_id] = dev
                cnt_of_devices += 1
            self._logger.info(f"Loaded {cnt_of_devices} devices")
        except Exception as e:
            self._logger.error(f"Error loading: {e}")

    def make_hum_name_to_id(self):
        self._name_to_id = {dev.friendly_name: dev_id for dev_id, dev in self._devices.items() if dev.friendly_name}

    def set_id_to_friendly_name(self, friendly_name: str, dev_id: str):
        self._name_to_id[friendly_name] = dev_id

    def join_local_and_cloud_configs(
        self,
        cloud_devs_conf: list,
        devices_id_to_add: List[str] | None,
    ) -> tuple[list, list]:
        
        local_scan_devices = self.read(const.LOCAL_SCAN_FILE)
        if not local_scan_devices:
            raise FileNotFoundError("local_scan.json file not found")
        
        joined_devs = []
        new_devices_conf = []

        for dev_obj in cloud_devs_conf:
            for key in local_scan_devices.keys():
                if "Error" in local_scan_devices[key]: continue
                if dev_obj["id"] in local_scan_devices[key]["gwId"]:
                    dev_obj["ip"] = local_scan_devices[key]["ip"]
                    dev_obj["version"] = local_scan_devices[key]["version"]
                    joined_devs.append(dev_obj)

        add_only = set(devices_id_to_add) if devices_id_to_add else set()

        current_devices_conf = self.read(const.DEVICES_CONF_FILE)
        if current_devices_conf:
            present = {d["id"] for d in current_devices_conf}
            for dev in joined_devs:
                dev_id = dev.get("id")
                if dev_id not in present and (dev_id in add_only):
                    current_devices_conf.append(dev)
                    new_devices_conf.append(dev)
            joined_devs = current_devices_conf
        else:
            filtered_joined_devs = []
            for device in joined_devs:
                if device["id"] in devices_id_to_add:
                    filtered_joined_devs.append(device)
            
            joined_devs = filtered_joined_devs

        return new_devices_conf, joined_devs

    def _insert_unknown_dp_number(self, tuya_device_id: str, dp_num: str):
        devs_conf_tmp = []
        devs_conf = self.read(const.DEVICES_CONF_FILE)
        for dev in devs_conf:
            if dev["id"] == tuya_device_id:
                dev["mapping"][dp_num] = {"code": dp_num, "type": "Unknown", "values": {}}
            devs_conf_tmp.append(dev)
        self.load_devices(devs_conf_tmp)
        self.write(const.DEVICES_CONF_FILE, devs_conf_tmp)
        self._logger.info(f"Unknown DP {dp_num} add to device {tuya_device_id}")
    
    def make_device_brief(self, dev: dict) -> dict:
        """
        Compress «fat» config of Tuya-device to minimum set,
        which I hope enough to build UI-panel in front-end
        and to form true MQTT commands from back-end.
        """
        try:
            brief: dict = {
                "id":       dev.get("id", ""),
                "label":    dev.get("name", dev.get("id")),
                "friendly_name": dev.get("friendly_name", ""),
                "category": const.HRF_TUYA_DEVICE_CATEGORY.get(dev.get("category"), ""),
                "dp_map":   {},
            }
            for dpid, values in dev.get("mapping").items():
                dp_code_name = values.get("code", dpid)
                dp_info = const.HRF_DP_TYPES.get(dp_code_name)
                brief["dp_map"][dp_code_name] = dp_info
            return brief
        except Exception as e:
            self._logger.error(f"Unknown error _make_device_brief: {e}")
