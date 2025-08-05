# -*- coding: utf-8 -*-

import json
import time
import threading

import sys

import concurrent.futures

from core.tuya import tuya_constants as const
from core.mqtt_client_wrapper import MqttModule
from core.utility_functions import *

from extensions.homie.common.homie_device_model import HomieDevice
from extensions.homie.common.homie_bridge_adapter import DeviceBridge
from extensions.homie.common.tuya_to_homie_converter import TuyaHomieConverter, TemplateManager
from extensions.homie.lifecycle.homie_lifecycle_extension import Extension as HomieLifecycleExtension
from extensions.homie.homie_broadcast_extension import HomieBroadcastExtension
from core.settings_loader import load_settings

#------------------------------------
from core.logger_setup import configure_logger 
from extensions.metrics.metrics_collection_extension import Extension as MetricsExtension
from core.device_repository import DeviceStore
from core.signal_manager import SignalManager
from core.tuya.cloud.tuya_openapi_rest_client import CloudAPI
from core.tuya.discovery.tuya_udp_device_scanner import Scanner
#------------------------------------


class Tuya2MqttBridge:
    def __init__(self):
        self._logger = configure_logger()
        # Identifier used in MQTT topics
        self.service_id = const.SERVICE_ID
        self._config = load_settings("/home/tsmolyanin/wk/ttmp/tuya2mqtt/settings/config.toml")
        self._device_store = DeviceStore(self._logger)
        SignalManager(self._graceful_shutdown, self._logger).install()

        self._state = const.BridgeState.OFFLINE

        self._state_lock = threading.Lock() # to change flag frome diff threads

        self._mqtt = self._init_mqtt_module()
        tuya_devices_conf = self._device_store.read(const.DEVICES_CONF_FILE)

        if tuya_devices_conf:
            self._device_store.load_devices(tuya_devices_conf)
        
        self._device_store.make_hum_name_to_id()

        ext_cfg = self._config.get("extensions", {})
        homie_cfg = ext_cfg.get("homie", {})
        lifecycle_cfg = homie_cfg.get("lifecycle", {})
        if lifecycle_cfg.get("enabled", False):
            self._homie_converter = TuyaHomieConverter(TemplateManager("extensions/homie/common/templates/"))
            self._sync = HomieLifecycleExtension(
                self._mqtt, self._device_store, self._homie_converter, logger=self._logger
            )
        else:
            self._homie_converter = None
            self._sync = None

        broadcast_cfg = homie_cfg.get("broadcast", {})
        if broadcast_cfg.get("enabled", False) and self._sync:
            self._broadcast = HomieBroadcastExtension(
                self._mqtt, self._device_store, self._sync, logger=self._logger
            )
        else:
            self._broadcast = None
        
        self._tuya_cloud = CloudAPI(self._logger)

        if self._tuya_cloud:
            self._set_state(const.BridgeState.ONLINE)
        else:
            self._set_state(const.BridgeState.LAN_ONLY)

        self._scanner = Scanner(self._mqtt, self._tuya_cloud, self._logger, self._device_store)

        self._register_mqtt_handlers()
        self._shutdown_event = threading.Event()
        self._daemon_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)

        metrics_cfg = ext_cfg.get("metrics", {})
        if metrics_cfg.get("enabled", False):
            self._metrics = MetricsExtension()
        else:
            self._metrics = None

        self._test_all_devs_statuses = {}

    # ------------------------------------------------------------------
    # Homie 5 helpers
    # ------------------------------------------------------------------
    def _init_homie_bridges(self):
        """Create HomieDevice for each TuyaDevice currently known."""
        devices = self._device_store.get_devices()
        for dev_id, tuya_dev in devices.items():
            try:
                homie_id, desc = self._homie_converter.convert_device(tuya_dev.to_dict())
                holder = {}
                def _on_set(node, prop, val, _holder=holder):
                    if 'bridge' in _holder:
                        _holder['bridge'].on_set(node, prop, val)
                homie_dev = HomieDevice(
                    mqtt=self._mqtt,
                    dev_id=homie_id,
                    description=desc,
                    on_set=_on_set
                )
                bridge = DeviceBridge(tuya_dev, homie_dev, logger=self._logger)
                holder['bridge'] = bridge
                self._device_bridges[dev_id] = bridge
                self._logger.debug(f"HomieDevice created for {dev_id} → {homie_id}")
            except Exception as exc:
                self._logger.error(f"Failed to init Homie for {dev_id}: {exc}")

    def _init_mqtt_module(self):
        if const.MQTT_USERNAME and const.MQTT_PASSWORD:
            mqtt_mod = MqttModule(
                input_topics={},
                module_name="Tuya2MQTT",
                logger=self._logger,
                mqtt_broker_ip=const.MQTT_BROKER_HOST,
                mqtt_broker_port=const.MQTT_BROKER_PORT,
                username=const.MQTT_USERNAME,
                user_passwd=const.MQTT_PASSWORD
                )
        else:
            mqtt_mod = MqttModule(
                input_topics={},
                module_name="Tuya2MQTT",
                logger=self._logger,
                mqtt_broker_ip=const.MQTT_BROKER_HOST,
                mqtt_broker_port=const.MQTT_BROKER_PORT
            )
        return mqtt_mod
    
    def _register_mqtt_handlers(self):
        handlers = {
            f"{const.SERVICE_ID}/bridge/request/scan":          self.on_scan_command,
            f"{const.SERVICE_ID}/bridge/request/scan_gen":      self.on_scan_gen_command,
            f"{const.SERVICE_ID}/bridge/request/scan_gen_all":  self.on_scan_gen_all_command,
            f"{const.SERVICE_ID}/bridge/request/remove":        self.on_remove_device,
            f"{const.SERVICE_ID}/bridge/request/add":           self.on_add_devices,
            f"{const.SERVICE_ID}/bridge/request/update_key":    self.on_update_device_key,
            f"{const.SERVICE_ID}/bridge/request/friendly_name": self.on_friendly_name,
            f"{const.SERVICE_ID}/bridge/request/stop_scan":     self.on_stop_scan,
            f"{const.SERVICE_ID}/bridge/request/scan_time":     self.on_set_scan_time,
            f"{const.SERVICE_ID}/devices/+/set":                self.on_device_command,
        }
        self._mqtt.update_topic_handlers(handlers)

    def start(self):
        self._logger.info("Tuya2MQTT bridge started as daemon thread")
        self._mqtt.mqtt_module_start(run_method="daemon")

        if self._sync:
            self._sync.on_bridge_start(self)
        if self._broadcast:
            self._broadcast.on_bridge_start(self)
        if self._metrics:
            self._metrics.on_bridge_start(self)

        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

        self._publish_bridge_status()

        try:
            self._shutdown_event.wait() 
        except KeyboardInterrupt:
            self._logger.info("Ctrl+C received")

    # MQTT HANDLERS
    @require_state(const.BridgeState.LAN_ONLY, const.BridgeState.ONLINE)
    def on_device_command(self, *args):
        
        topic, payload = args[0], args[1]
        parts = topic.split("/")
        ident = parts[2]

        if ident in self._device_store.get_devices():
            dev_id = ident
        elif ident in self._device_store.get_devices_friendly_name():
            dev_id = self._device_store.get_devices_friendly_name[ident]
        else:
            self._logger.warning(f"Unknown device identifier {ident}")
            return

        tuya_device = self._device_store.get_devices(dev_id)

        if not tuya_device:
            self._logger.warning(f"Unknown device {dev_id} in on_device_command")
            return
        try:
            actions = json.loads(payload)
            api_ver = actions.pop("api_ver")
            if api_ver and api_ver == 2:
                self._handel_apiv2_methods(actions, tuya_device, dev_id)
            else:
                self._handel_apiv1_methods(actions, tuya_device, dev_id)
        except KeyError as kerr:
            self._handel_apiv1_methods(actions, tuya_device, dev_id)
        except Exception as e:
            self._logger.error(f"Command error for {dev_id}: {e}")

    def on_friendly_name(self, *args):
        """
        payload: {"device_id":"<id>", "friendly_name":"<name>"}
        """
        self._logger.info("Received SET FRIENDLY NAME request via MQTT.")
        self._daemon_thread_pool.submit(self._set_friendly_name, *args)

    @require_state(const.BridgeState.LAN_ONLY, const.BridgeState.ONLINE)
    def on_scan_command(self, *args):
        """
        payload: ""
        """
        self._logger.info("Received SCAN request via MQTT.")
        self._daemon_thread_pool.submit(self._scanner.scan_local_network)

    @require_state(const.BridgeState.LAN_ONLY, const.BridgeState.ONLINE)
    def on_scan_gen_command(self, *args):
        """
        payload: ""
        """
        self._logger.info("Received SCAN request via MQTT.")
        _, scan_time_obj = args[0], json.loads(args[1])
        if not scan_time_obj:
            scan_time = None
        else:
            scan_time = scan_time_obj["scan_time"]
        self._daemon_thread_pool.submit(self._scanner.scan_gen_local_network, scan_time)
    
    @require_state(const.BridgeState.LAN_ONLY, const.BridgeState.ONLINE)
    def on_scan_gen_all_command(self, *args):
        """
        payload: ""
        """
        self._logger.info("Received SCAN request via MQTT.")
        _, scan_time_obj = args[0], json.loads(args[1])
        if not scan_time_obj:
            scan_time = None
        else:
            scan_time = scan_time_obj["scan_time"]
        self._daemon_thread_pool.submit(self._scanner.scan_gen_all_local_network, scan_time)
    
    @require_state(const.BridgeState.ONLINE)
    def on_add_devices(self, *args):
        self._logger.info("Received ADD devices request via MQTT.")
        self._daemon_thread_pool.submit(self._add_devices, *args)
    
    def on_remove_device(self, *args):
        self._logger.info("Received REMOVE devices request via MQTT.")
        self._daemon_thread_pool.submit(self._remove_device, *args)
    
    @require_state(const.BridgeState.ONLINE)
    def on_update_device_key(self, *args):
        """
        payload: {"device_id": "<id1>"}
        """
        self._logger.info("Received UPDATE DEVICE KEY request via MQTT.")
        self._daemon_thread_pool.submit(self._update_device_key, *args)
    
    def on_stop_scan(self, *args):
        self._logger.info("Received STOP GEN SCAN request via MQTT.")
        self._scanner.stop_scan()
    
    def on_set_scan_time(self, *args):
        """
        payload: {"device_id":"<id>", "friendly_name":"<name>"}
        """
        self._logger.info("Received SET SCAN TIME request via MQTT.")
        _, scan_time = args[0], json.loads(args[1])["time"]
        self._scanner.set_scan_time(int(scan_time))
    
    ########################################################################

    def _handel_apiv1_methods(self, actions: dict, tuya_device, dev_id):
        """
         {"api_ver": 1, "switch": True, "bright": 100}
         or
         {"switch": True, "bright": 100}
        """
        for cmd, payload in actions.items():
            match cmd:
                case "bright":
                    tuya_device.set_bright_async(payload)
                case "color_temp":
                    tuya_device.set_temperature_async(payload)
                case "color_hsv":
                    tuya_device.set_color_hsv_async(payload)
                case "color_rgb":
                    tuya_device.set_color_rgb_async(payload)
                case "work_mode":
                    if payload in const.TUYA_DEVICE_MODES:
                        tuya_device.set_mode_async(payload)
                    else:
                        self._logger.warning(f"Unknown mode {payload} for device {dev_id}")
                case "scene":
                    pass
                case "switch":
                    tuya_device.switch_state_async(payload)
                case "toggle":
                    tuya_device.toggle_switch_state_async(payload)
    
    def _handel_apiv2_methods(self, actions: dict, tuya_device, dev_id):
        """
         {"api_ver": 2, "switch_led": True, "switch": True}
        """
        tuya_device.set_status_async(actions)

    def _add_devices(self, *args):
        response_topic = "tuya2mqtt/bridge/response/add"

        _, payload = args[0], args[1]
        tuya_devices_id_list = json.loads(payload)["device_ids"]
        
        if not tuya_devices_id_list:
            self._mqtt.mqtt_publish_value_to_topic(response_topic, [])
            raise ValueError("No one Tuya Device ID was given")
        
        device_id_list = ", ".join(tuya_devices_id_list)
        self._tuya_cloud.set_device_id(device_id_list)

        tuya_cloud_answer = {}
        self._logger.info("Calling cloud.getdevices(include_map=True)...")
        try:
            tuya_cloud_answer =  self._tuya_cloud.tuya_cloud_request()
            if "Error" in tuya_cloud_answer:
                error = tuya_cloud_answer["Error"]
                payload = tuya_cloud_answer["Payload"]
                self._logger.error(f"{error} for device IDs: {tuya_devices_id_list}. {payload}")
                self._mqtt.mqtt_publish_value_to_topic(response_topic, tuya_cloud_answer)
                return
        except Exception as e:
            self._logger.error(f"Exception calling cloud.getdevices: {e}")
            return
        try:
            new_devices_conf, joined_devices_config = self._device_store.join_local_and_cloud_configs(
                tuya_cloud_answer, tuya_devices_id_list
            )
            if not isinstance(new_devices_conf, list):
                new_devices_conf = []
            self._device_store.write(const.DEVICES_CONF_FILE, joined_devices_config)
            self._device_store.load_devices(joined_devices_config)
            self._device_store.make_hum_name_to_id()
            if self._sync:
                updated_new_devices = [
                    self._device_store.get_devices(dev["id"]).to_dict() for dev in new_devices_conf
                ]
                self._sync.on_devices_added(updated_new_devices)
            if new_devices_conf:
                response = [self._device_store.make_device_brief(dev) for dev in new_devices_conf]
            else:
                response = [self._device_store.make_device_brief(dev) for dev in joined_devices_config]
            self._mqtt.mqtt_publish_value_to_topic(response_topic, response)
        except FileNotFoundError as ferr:
            self._logger.error(ferr)

    def _remove_device(self, *args):
        """
        payload: {"device_ids":["<id1>", "<id2>", "<id3>" ...]}
        """
        response_topic = "tuya2mqtt/bridge/response/remove"
        removed_devices = []
        _, payload = args[0], args[1]
        try:
            device_ids = json.loads(payload)["device_ids"]
            for dev_id in device_ids:
                if dev_id in self._device_store.get_devices():
                    tuya_dev = self._device_store.get_devices(dev_id)
                    if tuya_dev:
                        tuya_dev.stop_worker()
                        tuya_dev.join()
                    
                    self._device_store.remove_device(dev_id)
                    removed_devices.append(dev_id)

                    devs_conf_tmp = []
                    devs_conf = self._device_store.read(const.DEVICES_CONF_FILE)
                    for dev in devs_conf:
                        if dev["id"] != dev_id:
                            devs_conf_tmp.append(dev)
                    
                    self._device_store.write(const.DEVICES_CONF_FILE, devs_conf_tmp)
            
            self._logger.info(f"Removed device {removed_devices}")
            if self._sync:
                for d in removed_devices:
                    self._sync.on_device_removed(d)
            response = {"device_ids": removed_devices}
            self._mqtt.mqtt_publish_value_to_topic(response_topic, response)
        except Exception as e:
            self._logger.error(f"Unknown error while removing device: {e}")
    
    def _set_friendly_name(self, *args):
        """
        payload: {"device_id":"<id>", "friendly_name":"<name>"}
        """
        try:
            _, payload = args[0], args[1]
            data = json.loads(payload)
            dev_id = data["device_id"]
            friendly_name = data["friendly_name"]
            if dev_id not in self._device_store.get_devices():
                self._logger.error(f"Friendly name: unknown device {dev_id}")
                return

            self._device_store.get_devices(dev_id).friendly_name = friendly_name
            self._device_store.set_id_to_friendly_name(friendly_name, dev_id)

            devs_conf_tmp = []
            devs_conf = self._device_store.read(const.DEVICES_CONF_FILE)
            for dev in devs_conf:
                if dev["id"] == dev_id:
                    dev["friendly_name"] = friendly_name
                devs_conf_tmp.append(dev)
            self._device_store.load_devices(devs_conf_tmp)
            self._device_store.write(const.DEVICES_CONF_FILE, devs_conf_tmp)

            if self._sync:
                self._sync.on_device_renamed(dev_id, friendly_name)
            self._logger.info(f"Set friendly_name for {dev_id} → {friendly_name}")
        except Exception as e:
            self._logger.error(f"Error in on_friendly_name: {e}")
    
    def _update_device_key(self, *args):
        """
        payload: {"device_id": "<id1>"}
        """
        response_topic = "tuya2mqtt/bridge/response/update_key"

        _, tuya_device_id = args[0], json.loads(args[1])["device_id"]
        self._tuya_cloud.set_device_id(tuya_device_id)

        tmp_dict = self._device_store.get_devices(tuya_device_id).to_dict()
        local_key = tmp_dict["key"]

        self._logger.info(f"Update local key for device {tuya_device_id}") 
        try:
            tuya_cloud_devices = self._tuya_cloud.tuya_cloud_request()
            if "Error" in tuya_cloud_devices: return
            # print(tuya_cloud_devices)
            for dev in tuya_cloud_devices:
                if dev["id"] == tuya_device_id:
                    local_key = dev["key"]
            
            devs_conf_tmp = []
            devs_conf = self._device_store.read(const.DEVICES_CONF_FILE)
            for dev in devs_conf:
                if dev["id"] == tuya_device_id:
                    dev["key"] = local_key
                devs_conf_tmp.append(dev)
            self._device_store.load_devices(devs_conf_tmp)
            self._device_store.write(const.DEVICES_CONF_FILE, devs_conf_tmp)
            if self._sync:
                self._sync.on_device_key_changed(tuya_device_id)
            self._logger.info(f"Local key for device {tuya_device_id} updated with {local_key}") 
            self._mqtt.mqtt_publish_value_to_topic(response_topic, local_key)
        except Exception as e:
            self._logger.error(f"Exception calling cloud.getdevices: {e}")
            return

    # def _check_network(self, *args):
    #     self._set_state(_determine_net_state())
    
    def _poll_loop(self):
        """Deamon Thread: every POLL_INTERVAL seconds send tasks."""
        while not self._shutdown_event.is_set():
            try:
                for device_id, device_obj in self._device_store.get_devices().items():
                    device_obj.update_status_async(self._handle_devices_status)
                    if self._metrics:
                        self._metrics.inc_total()
                time.sleep(const.POLL_INTERVAL)
            except Exception as e:
                if self._metrics:
                    self._metrics.record_error(str(type(e)))
                self._logger.error(f"Error polling {device_id}: {e}")
    
    def _handle_devices_status(self, *args):
        device_id, raw_feedback, estimated_time = args
        if "Error" in raw_feedback:
            self._handle_error_answer(device_id, raw_feedback)
        else:
            human_readable_dps = self._parse_answer_from_devs(device_id, raw_feedback)
            human_readable_dps["request_status_time"] = round(estimated_time, 3)
            if estimated_time > 5:
                if self._metrics:
                    self._metrics.inc_slow()
            self._publish_device_status(device_id, human_readable_dps)
            # print(device_id, human_readable_dps)
            # print()

    def _publish_device_status(self, dev_id: str, dps: dict):
        # forward to Homie representation
        if self._sync:
            br = self._sync.device_bridges.get(dev_id)
            if br:
                br.publish_status(dps)
        topic = f"{const.SERVICE_ID}/devices/{dev_id}/status"
        self._mqtt.mqtt_publish_value_to_topic(topic, json.dumps(dps))
        """
        @ ADDED FOR TEST 
        """
        self._test_all_devs_statuses[dev_id] = dps
        test_topic_for_all_statuses = f"{const.SERVICE_ID}/devices/statuses"
        self._mqtt.mqtt_publish_value_to_topic(test_topic_for_all_statuses, json.dumps(self._test_all_devs_statuses))
    
    def _parse_answer_from_devs(self, dev_id: str, data: dict):
        tmp_dict = {}
        dps = data.get("dps")
        if dev_id not in self._device_store.get_devices():
            return {}
        try:
            device = self._device_store.get_devices(dev_id)
            for dp_num, dp_num_value in dps.items():
                dp_desc = device.get_mapping().get(dp_num)
                if dp_desc:
                    dp_human_name = dp_desc.get("code", dp_num)
                    tmp_dict[dp_human_name] = dp_num_value
                else:
                    self._device_store._insert_unknown_dp_number(dev_id, dp_num)
        
            if tmp_dict.get("bright_value", ""):
                tmp_dict["bright_value"] = self._transform_tuya_format_to_percents({"bright_value": tmp_dict["bright_value"]})
            if tmp_dict.get("bright_value_v2", ""):
                tmp_dict["bright_value_v2"] = self._transform_tuya_format_to_percents({"bright_value_v2": tmp_dict["bright_value_v2"]})
            if tmp_dict.get("temp_value", ""):
                tmp_dict["temp_value"] = self._transform_tuya_format_to_percents({"temp_value": tmp_dict["temp_value"]})
            if tmp_dict.get("temp_value_v2", ""):
                tmp_dict["temp_value_v2"] = self._transform_tuya_format_to_percents({"temp_value_v2": tmp_dict["temp_value_v2"]})

            return tmp_dict
        except AttributeError as attrerror:
            self._logger.error(f"Error while _parse_answer_from_devs: {attrerror}")
            self._device_store.get_devices(dev_id).stop_worker()

    def _handle_error_answer(self, dev_id, raw_data):
        err_code = raw_data.get("Err")
        error_data = {}
        try:
            for err_name, err_desc in raw_data.items():
                if isinstance(err_name, str):
                    err_name = err_name.lower()
                error_data[err_name] = err_desc
        except AttributeError as attr_er:
            self._logger.error(f"Unknown error code {err_code} from {dev_id}")
        if self._metrics:
            self._metrics.record_error(f"ERR_{err_code}")
        self._publish_device_status(dev_id, error_data)
        try:
            err = const.ErrorStatus(err_code)
        except ValueError:
            self._logger.error(f"Unknown error code {err_code} from {dev_id}")
            return
        match err:
            case const.ErrorStatus.ERR_CONNECT:
                # self._publish_device_remove(dev_id)
                pass
            case const.ErrorStatus.ERR_KEY_OR_VER:
                self._publish_device_update_key(dev_id)
    
    def _transform_tuya_format_to_percents(self, parameter: dict) -> int:
        """
        Transform «raw» values of Tuya-devices (bright and color_temp) to percents (0-100).
        parameter : dict
            * ``{"bright_value | bright_value_v2": <int>}``     - bright, Tuya range 10-1000  
            * ``{"temp_value | temp_value_v2": <int>}`` - temperature color Tuya range 0-1000  
        """
        parameter_name, value = next(iter(parameter.items()))
        match parameter_name:
            case "bright_value" | "bright_value_v2":
                # Tuya 10-1000
                MIN_RAW, MAX_RAW = 10, 1000
                if value < MIN_RAW:
                    return 0
                if value > MAX_RAW:
                    return 100
                return int((value - MIN_RAW) * 100 / (MAX_RAW - MIN_RAW))

            case "temp_value" | "temp_value_v2":
                # Tuya 0-1000
                if value <= 0:
                    return 0
                if value >= 1000:
                    return 100
                return int(value / 10)
            case _:
                self._logger.warning(f"Unknown parameter key '{parameter_name}' for percent conversion")
                return -1
        return -1 
        
    def _publish_device_remove(self, dev_id: str):
        topic = f"{const.SERVICE_ID}/bridge/request/remove"
        payload = json.dumps({"device_ids": [dev_id]})
        self._mqtt.mqtt_publish_value_to_topic(topic, payload)

    def _publish_device_update_key(self, dev_id: str):
        topic = f"{const.SERVICE_ID}/bridge/request/update_key"
        payload = json.dumps({"device_id": dev_id})
        self._mqtt.mqtt_publish_value_to_topic(topic, payload)
    
    def _set_state(self, new_state: const.BridgeState):
        with self._state_lock:
            if new_state != self._state:
                self._state = new_state
                self._logger.info(f"Bridge state → {new_state.name}")
                self._publish_bridge_status()
    
    def _publish_bridge_status(self):
        topic = f"{const.SERVICE_ID}/bridge/status"
        self._mqtt.mqtt_publish_value_to_topic(topic, self._state.name)
    
    def _graceful_shutdown(self):
        """Stop all what we must and exit from process"""

        self._shutdown_event.set()
        self._logger.debug("Shutdown-event-flag is set")

        # Shutdown all daemon threads of TuyaDevice
        for device in  self._device_store.get_devices().values():
            device.stop_worker()
        self._logger.debug("All daemon threads of TuyaDevice stoped")

        self._daemon_thread_pool.shutdown(wait=False, cancel_futures=True)
        self._logger.debug("ThreadPoolExecutor stoped")

        if self._sync:
            self._sync.on_bridge_stop(self)
        if self._metrics:
            self._metrics.on_bridge_stop(self)

        # Stop the MQTT client
        try:
            self._mqtt.stop()
        except Exception as exc:
            self._logger.error(f"An error during to stop MQTT client: {exc}")
        
        sys.exit(0)


if __name__ == "__main__":
    bridge = Tuya2MqttBridge()
    bridge.start()
    # from tuya_to_homie5 import TuyaHomieConverter, TemplateManager
    # from homie_sync import Extension
    # from pprint import pprint

    # conv = TuyaHomieConverter(template_manager=TemplateManager("extensions/homie/common/templates/"))
    
    # with open("devices.json", "r") as fh:
    #     tuya_data = json.load(fh)

    # homie_desc = conv.convert_devices(tuya_data)
    
    # pprint(homie_desc)
    # with open("homie5_test.json", "w") as fh:
    #     json.dump(homie_desc, fh, indent=4)