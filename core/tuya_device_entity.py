# -*- coding: utf-8 -*-
import time
import threading
import queue
import itertools

# import tinytuya
import core.tuya.tuya_constants as tinytuya
from core.tuya.local.tinytuya_local_transport import TinyLocalTransport

class TuyaDevice:
    def __init__(self, dev_id, ip=None, local_key=None, product_id=None,
                 version="3.4", category="", mapping=None, friendly_name: str = None):
        self.dev_id = dev_id
        self.friendly_name = friendly_name
        self.ip = ip
        self.local_key = local_key
        self.product_id = product_id
        self.version = version
        self.category = category
        self.mapping = mapping if mapping else {}
        self.tuya_dev = None
        self.is_type_c = False

        self._last_status = {}

        self._cmd_queue = queue.PriorityQueue()
        self._counter = itertools.count()
        self._cmd_thread = threading.Thread(target=self._worker, daemon=True, name=f"TuyaDevice-{self.dev_id}-worker")
        self._stop_worker_flag = threading.Event()
        if self.ip and self.local_key:
            self._init_tinytuya()
            self._detect_type_c()
        
        self._cmd_thread.start()
        
    def _init_tinytuya(self):
        """Теперь создаём *адаптер*, а не прямой объект tinytuya."""
        self.tuya_dev = TinyLocalTransport(
            dev_id=self.dev_id,
            ip=self.ip,
            local_key=self.local_key,
            category=self.category,
            version=self.version,
            connection_timeout=5,
            connection_retry_limit=2,
            connection_retry_delay=1,
        )
        self.tuya_dev.set_socketPersistent(False)

    def _worker(self):
        while not self._stop_worker_flag.is_set():
            priority, _, function, args, callback, enq_time, ttl = self._cmd_queue.get()
            
            # check TTL
            if time.monotonic() - enq_time > ttl:
                # not fresh cmd - drop it
                self._cmd_queue.task_done()
                continue
            try:
                send_cmd_start = time.perf_counter()
                feedback = function(*args)
                time_to_send_cmd = time.perf_counter() - send_cmd_start
            except Exception as e:
                feedback = {"Error": e}
                if callback:
                    callback(self.dev_id, feedback)
            if callback:
                callback(self.dev_id, feedback, time_to_send_cmd)
            self._cmd_queue.task_done()

    def stop_worker(self, timeout: float = 1.0):
        self._stop_worker_flag.set()

        sentinel = (0, 0, lambda *a, **kw: None, (), None)
        self._cmd_queue.put(sentinel)

        try:
            while True:
                self._cmd_queue.get_nowait()
                self._cmd_queue.task_done()
        except queue.Empty:
            pass
    
    def _enqueue(self, fn, *args, callback=None, priority=0, ttl=None):
        """
        priority: 0=управление, 1=опрос статуса
        ttl:        seconds before dropping this task
        """
        enqueue_time = time.monotonic()
        # если ttl не передали, ставим по-умолчанию в зависимости от приоритета
        if ttl is None:
            ttl = 0.8 if priority == 1 else 5.0
        
        count = next(self._counter)
        self._cmd_queue.put((priority, count, fn, args, callback, enqueue_time, ttl))

    def to_dict(self):
        data = {
            "id": self.dev_id,
            "ip": self.ip,
            "key": self.local_key,
            "product_id": self.product_id,
            "version": self.version,
            "category": self.category,
            "mapping": self.mapping
        }
        if self.friendly_name:
            data["friendly_name"] = self.friendly_name
        return data

    def get_mapping(self):
        return self.mapping

    @staticmethod
    def from_dict(d):
        return TuyaDevice(
            dev_id=d["id"],
            ip=d.get("ip"),
            local_key=d.get("key"),
            product_id=d.get("product_id"),
            version=d.get("version", "3.4"),
            category=d.get("category", ""),
            mapping=d.get("mapping", {}),
            friendly_name=d.get("friendly_name")
        )

    # High-priority commands (priority=0)
    def switch_state_async(self, payload):
        self._enqueue(self._switch_state, payload)
    
    def set_bright_async(self, payload):
        self._enqueue(self._set_brightness_percent, payload)

    def set_color_hsv_async(self, payload):
        self._enqueue(self._set_color_hsv, payload)
    
    def set_color_rgb_async(self, payload):
        self._enqueue(self._set_color_rgb, payload)
    
    def set_temperature_async(self, payload):
        self._enqueue(self._set_temperature, payload)
    
    def set_mode_async(self, payload):
        self._enqueue(self._set_device_mode, payload)
    
    def toggle_switch_state_async(self, payload):
        self._enqueue(self._toggle_switch_state, payload)
    
    def set_status_async(self, payload):
        self._enqueue(self._set_device_status, payload)
    
    # Low-priority command (status polling, priority=1)
    def update_status_async(self, publish_fn):
        self._enqueue(self._update_status, callback=publish_fn, priority=1)
    
    ####################################################

    def _set_device_status(self, payload):
        data = {}
        for dp_code_hrf, value in payload.items():
            for dp_code, mapping in self.mapping.items():
                if mapping["code"] == dp_code_hrf:
                    if value == "toggle":
                        data[dp_code] = self._toggle_switch_state(dp_code)
                    else:
                        dp_type = mapping["type"]
                        dp_values = mapping["values"]
                        data[dp_code] = self._value_from_device_type(dp_type, dp_values, value)
        payloadd = self.tuya_dev.generate_payload(tinytuya.CONTROL, data)
        self.tuya_dev.send(payloadd)

    def _value_from_device_type(self, type: str, values: dict, in_value):
        match type:
            case "Boolean":
                return in_value
            case "Integer":
                min_val, max_val = values["min"], values["max"]
                return self._scale_input_from_percents(min_val, max_val, in_value)
            case "Json":
                ...

    def _set_device_mode(self, payload):
        self.tuya_dev.set_mode(mode=payload)

    def _set_color_hsv(self, payload):
        h, s, v = payload[0], payload[1], payload[2]
        self.tuya_dev.set_hsv(h, s, v)
    
    def _set_color_rgb(self, payload):
        r, g, b = payload[0], payload[1], payload[2]
        self.tuya_dev.set_colour(r, g, b)
    
    def _set_temperature(self, payload):
        self.tuya_dev.set_colourtemp_percentage(payload)
    
    def _update_status(self):
        if not self.tuya_dev:
            return {}
        data = self.tuya_dev.status()
        self._last_status = data.get("dps", {})
        return data

    def _detect_type_c(self):
        try:
            dps = self.get_mapping()
            if dps.get("2"):
                dp2_name = dps.get("2")["code"]
                if "bright" in dp2_name:
                    self.is_type_c = True
        except Exception as e:
            raise BaseException(e)
    
    def _set_brightness_percent(self, brightness: int):
        if not self.is_type_c:
            self.tuya_dev.set_brightness_percentage(brightness)
        else:
            brightness_value = 0
            if brightness <= 0: brightness_value = 10
            elif brightness >= 100: brightness_value = 1000
            else: brightness_value = int(10 + (1000 - 10) * brightness / 100)
            self.tuya_dev.set_value(2, brightness_value)
    
    def _switch_state(self, payload):
        if isinstance(payload, bool):
            if payload:
                self.tuya_dev.turn_on()
            else:
                self.tuya_dev.turn_off()
        elif isinstance(payload, dict):
            state = payload["state"]
            switch_num = payload["switch_num"]
            self.tuya_dev.set_status(state, switch_num)

    def _toggle_switch_state(self, dp_code):
        status = self._last_status[dp_code]
        if status:
            return False
        return True
    
    def _scale_input_from_percents(self, min: int, max: int, percents_value):
        
        if isinstance(percents_value, str):
            try:
                percents_value = int(float(percents_value))
            except ValueError:
                percents_value = -1
        try:
            perc = int(percents_value)
        except Exception:
            perc = -1
        if min == max:
            return min
        if perc <= 0:
            return min
        if perc >= 100:
            return max
        total_range = max - min
        scaled_value = (perc * total_range + 50) // 100
        return min + scaled_value



    def __repr__(self):
        return f"{self.to_dict()}"