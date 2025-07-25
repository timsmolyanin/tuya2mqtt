import json
from collections import OrderedDict
import util
import const
import threading
import socket
import json
import select
import time
import threading
from adapters import tuya_constants
import tinytuya

UDPPORT = tuya_constants.UDPPORT          # Tuya 3.1 UDP Port
UDPPORTS = tuya_constants.UDPPORTS        # Tuya 3.3 encrypted UDP Port
UDPPORTAPP = tuya_constants.UDPPORTAPP    # Tuya app encrypted UDP Port


class Scanner:
    """Инкапсулирует все три варианта скана локальной сети + мердж с облаком."""
    def __init__(self, mqtt, cloud_api, logger, device_store, scan_time: int = 15):
        self._mqtt = mqtt
        self._tuya_cloud = cloud_api
        self._logger = logger
        self._scan_time = scan_time
        self._stop_scan_event = threading.Event()
        self._device_store = device_store
        self._DEFAULT_SCAN_TIME = 15
    
    def stop_scan(self):
        self._stop_scan_event.set()
    
    def set_scan_time(self, scan_time: int | None):
        if scan_time is None:
            self._scan_time = self._DEFAULT_SCAN_TIME
            return
        self._scan_time = scan_time
    
    def scan_local_network(self):
        response_topic = "tuya2mqtt/bridge/response/scan"
        self._logger.info("Starting scan local network.")
        try:
            # @ Need to remove tinytuya function deviceScan 
            devices = devices = tinytuya.deviceScan()
            self._process_basic_scan(devices, response_topic)
            self._logger.info("Scan local network finished")
        except OSError as oserror:
            if oserror.errno == 101:
                self._logger.error(f"{oserror.errno}: {oserror.strerror}")
                # self._set_state(const.BridgeState.OFFLINE)
        except Exception as e:
            self._logger.error(f"Unknown error scan local devices: {e}")

    def scan_gen_local_network(self, scan_time: int | None):
        response_topic = "tuya2mqtt/bridge/response/scan_gen"
        self._logger.info("Starting SCAN local network by generator func.")
        self.set_scan_time(scan_time)
        results = {}
        if self._stop_scan_event.is_set():
            self._stop_scan_event.clear()
        try:
            gen = self._scan_local_network_gen(
                verbose=False,
                scantime=self._scan_time,
                color=False,
                poll=False
            )
            for device in gen:
                merged_device = next(self._merge_scan_with_cloud(device), None)
                if merged_device:
                    self._mqtt.mqtt_publish_value_to_topic(
                    response_topic,
                    json.dumps(merged_device))
                    results.update(merged_device)
            if not results:
                self._mqtt.mqtt_publish_value_to_topic(
                    response_topic,
                    json.dumps({})
                )
            self._update_local_scan_file(results)
            self._logger.info("SCAN local network by generator func finished")
            # self._stop_scan_event.clear()
        except OSError as oserror:
            if oserror.errno == 101:
                self._logger.error(f"{oserror.errno}: {oserror.strerror}")
                # self._set_state(const.BridgeState.OFFLINE)
        except Exception as e:
            self._logger.error(f"Unknown error scan local devices: {e}")
    
    def scan_gen_all_local_network(self, scan_time: int | None):
        """
        Generator-based full-scan: incrementally publishes the entire
        set of discovered devices on each new detection, preserving insertion order.
        """
        response_topic = "tuya2mqtt/bridge/response/scan_gen_all"
        self._logger.info("Starting SCAN ALL local network by generator func.")
        self.set_scan_time(scan_time)
        if self._stop_scan_event.is_set():
            self._stop_scan_event.clear()
        try:
            gen = self._scan_local_network_gen(
                verbose=False,
                scantime=self._scan_time,
                color=False,
                poll=False
            )
            all_results = OrderedDict()
            for device in gen:
                merged_device = next(self._merge_scan_with_cloud(device), None)
                if merged_device:
                # Add to cumulative OrderedDict and publish full snapshot
                    all_results.update(merged_device)
                    self._mqtt.mqtt_publish_value_to_topic(
                        response_topic,
                        json.dumps(all_results)
                    )
            if not all_results:
                self._mqtt.mqtt_publish_value_to_topic(
                    response_topic,
                    json.dumps({})
                )
            # Persist full scan and clear stop event
            self._update_local_scan_file(all_results)
            # self._stop_scan_event.clear()
            self._logger.info("SCAN ALL local network by generator func finished")
        except OSError as oserror:
            if oserror.errno == 101:
                self._logger.error(f"{oserror.errno}: {oserror.strerror}")
                # self._set_state(const.BridgeState.OFFLINE)
        except Exception as e:
            self._logger.error(f"Unknown error scan local devices: {e}")


    def _process_basic_scan(self, local_scan_data, response_topic):
        """
        Common logic to process local network devices and merge with cloud data.

        :param devices_iterable: An iterable of (ip, device_data) tuples.
        :param response_topic: MQTT topic to publish each device's scan result.
        """
        if not local_scan_data:
            self._mqtt.mqtt_publish_value_to_topic(
                response_topic,
                json.dumps({})
            )
            self._update_local_scan_file({})
            return
        results = {}
        for data in self._merge_scan_with_cloud(local_scan_data):
            results.update(data)
        
        self._mqtt.mqtt_publish_value_to_topic(
                response_topic,
                json.dumps(results)
            )    
        if not results:
            self._mqtt.mqtt_publish_value_to_topic(
                response_topic,
                json.dumps({})
            )
        self._update_local_scan_file(results)
    
    def _merge_scan_with_cloud(self, scan_data):
        for ip, data in scan_data.items():
            # Initialize entry and attempt cloud merge
            dev_id = data.get("id")
            if dev_id not in self._device_store.get_devices():
                entry = {**data, "merge_with_cloud": False}
                self._tuya_cloud.set_device_id(data.get("id"))
                cloud_resp = self._tuya_cloud.tuya_cloud_request()

                if isinstance(cloud_resp, dict) and any(k in cloud_resp for k in ("Err", "Error")):
                    # Cloud error: keep only id and error info
                    entry = {**cloud_resp, "id": data.get("id")}
                else:
                    # Merge with matching cloud device
                    for cloud_dev in cloud_resp or []:
                        if data.get("id") == cloud_dev.get("id"):
                            entry["merge_with_cloud"] = True
                            entry.update({
                                "name": cloud_dev.get("name"),
                                "product_name": cloud_dev.get("product_name"),
                                "mac": cloud_dev.get("mac"),
                                "icon": cloud_dev.get("icon"),
                            })
                            break
                yield {ip: entry}
        
    def _update_local_scan_file(self, local_scan_data):
        saved_local_scan = self._device_store.read(const.LOCAL_SCAN_FILE)
        if not saved_local_scan:
            saved_local_scan = {}
        for ip, dev_data in local_scan_data.items():
            if ip not in saved_local_scan:
                saved_local_scan[ip] = dev_data
        
        self._device_store.write(const.LOCAL_SCAN_FILE, saved_local_scan)
        
    def _scan_local_network_gen(self, verbose=False, scantime=None, color=True, poll=True, forcescan=False, 
                   byID=False, show_timer=None, discover=True, wantips=None, 
                   wantids=None, snapshot=None, assume_yes=False, tuyadevices=[], 
                   maxdevices=0):
        """Scans network for Tuya devices and yields devices as they are found"""
        # Lookup Tuya device info by (id) returning (name, key)
        def tuyaLookup(deviceid):
            for i in tuyadevices:
                if "id" in i and i["id"] == deviceid:
                    return (i["name"], i["key"], i["mac"] if "mac" in i else "")
            return ("", "", "")
        
        # Enable UDP listeners
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        client.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        client.bind(("", UDPPORT))
        
        clients = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        clients.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        clients.bind(("", UDPPORTS))
        
        clientapp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        clientapp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        clientapp.bind(("", UDPPORTAPP))
        
        if scantime is None:
            scantime = tinytuya.SCANTIME
                    
        scan_end_time = time.time() + scantime
        broadcasted_devices = {}
        
        while time.time() < scan_end_time and not self._stop_scan_event.is_set():
            try:
                rd, _, _ = select.select([client, clients, clientapp], [], [], 1.0)
            except KeyboardInterrupt:
                print("\nScan stopped by user")
                break
            
            for sock in rd:
                if sock is client:
                    tgt_port = UDPPORT
                elif sock is clients:
                    tgt_port = UDPPORTS
                elif sock is clientapp:
                    tgt_port = UDPPORTAPP
                else:
                    continue
                    
                try:
                    data, addr = sock.recvfrom(4048)
                    ip = addr[0]
                    
                    # Skip if we already processed this device
                    if ip in broadcasted_devices:
                        continue
                        
                    try:
                        result = tinytuya.decrypt_udp(data)
                        result = json.loads(result)
                    except:
                        continue
                    
                    # Validate device info
                    if 'gwId' not in result:
                        continue
                        
                    # Get device details
                    (dname, dkey, mac) = tuyaLookup(result['gwId'])
                    result["name"] = dname
                    result["key"] = dkey
                    result["mac"] = mac
                    result["ip"] = ip
                    result["origin"] = "broadcast"
                    
                    if 'id' not in result:
                        result['id'] = result['gwId']
                        
                    # Format 20-digit IDs
                    if not mac and len(result['gwId']) == 20:
                        try:
                            mac = bytearray.fromhex(result['gwId'][-12:])
                            result["mac"] = '%02x:%02x:%02x:%02x:%02x:%02x' % tuple(mac)
                        except:
                            pass
                    
                    # Add to found devices
                    broadcasted_devices[ip] = result
                    
                    # Yield the device immediately
                    if byID:
                        yield {result['gwId']: result}
                    else:
                        yield {ip: result}
                                                
                except Exception as e:
                    print(f"Error processing device: {e}")
        
        # Close sockets
        client.close()
        clients.close()
        clientapp.close()