
import paho.mqtt.client as mqtt
import time
import logging
import threading
from typing import Callable, Any

class MqttModule:
    """Wrapper around *paho‑mqtt* with Homie‑friendly defaults.

    **Highlights**
    --------------
    * Keeps legacy method ``mqtt_publish_value_to_topic`` so existing code
      continues to work.
    * Uses QoS 2 + retain=True by default (Homie 5 requirements).
    * Configurable Last‑Will (usually ``homie/…/$state`` = ``lost``).
    * Dynamic handler registration even after the connection is up.
    * **New:** ability to tone down very chatty *paho* DEBUG logs
      (``paho_debug=False`` by default).
    """

    def __init__(
        self,
        input_topics: dict[str, Callable[[str, str], Any]] | None,
        module_name: str,
        logger: logging.Logger,
        mqtt_broker_ip: str = "127.0.0.1",
        mqtt_broker_port: int = 1883,
        username: str | None = None,
        user_passwd: str | None = None,
        *,
        # Homie additions
        lwt_topic: str | None = None,
        lwt_payload: str = "lost",
        lwt_qos: int = 2,
        lwt_retain: bool = True,
        # Logging
        paho_debug: bool = False,
    ):
        self._MODULE_NAME = module_name
        self._logger = logger
        self._BROKER_IP = mqtt_broker_ip
        self._BROKER_PORT = mqtt_broker_port
        self._USERNAME = username
        self._PASSWORD = user_passwd

        # ------------------------------------------------------------------
        # Paho logger configuration
        # ------------------------------------------------------------------
        paho_logger = logger.getChild("paho")
        paho_logger.setLevel(logging.DEBUG if paho_debug else logging.WARNING)
        # If we don't want DEBUG – stop propagation
        if not paho_debug:
            paho_logger.propagate = False

        # ------------------------------------------------------------------
        # Client
        # ------------------------------------------------------------------
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5
        )
        self._client.enable_logger(paho_logger)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        if lwt_topic:
            self._client.will_set(lwt_topic, lwt_payload, qos=lwt_qos, retain=lwt_retain)

        self._topic_handlers: dict[str, Callable[[str, str], Any]] = input_topics or {}
        self._stop = threading.Event()

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #
    def mqtt_module_start(self, run_method: str = "blocking") -> None:
        connected = self._connect()
        if not connected:
            return
        self._subscribe(initial=True)

        if run_method == "blocking":
            self._client.loop_forever()
        elif run_method == "daemon":
            self._client.loop_start()
        else:
            raise ValueError("run_method must be 'blocking' or 'daemon'")

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
        self._stop.set()
        self._logger.info("MQTT loop stopped.")

    # Legacy name kept
    mqtt_publish_value_to_topic = lambda self, t, v: MqttModule.publish(self, t, v)

    def publish(
        self,
        topic: str,
        payload: str | bytes,
        qos: int = 2,
        retain: bool = True,
    ) -> None:
        """Publish with Homie defaults (qos2+retain)."""
        p = payload if isinstance(payload, (bytes, bytearray)) else str(payload)
        try:
            self._client.publish(topic, p, qos=qos, retain=retain)
        except Exception as exc:
            self._logger.error(f"Failed to publish to {topic}: {exc}")

    def update_topic_handlers(self, mapping: dict[str, Callable[[str, str], Any]]) -> None:
        """Merge *mapping* into current handler table and (re)subscribe."""
        added = [t for t in mapping if t not in self._topic_handlers]
        self._topic_handlers.update(mapping)
        if added and self._client.is_connected():
            self._subscribe(extra=added)

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #
    def _connect(self) -> bool:
        retry = 5
        while not self._stop.is_set():
            try:
                if self._USERNAME:
                    self._client.username_pw_set(self._USERNAME, self._PASSWORD)
                self._client.connect(self._BROKER_IP, self._BROKER_PORT)
                self._logger.info("Connected to MQTT broker.")
                return True
            except Exception as exc:
                self._logger.warning(f"MQTT connect failed: {exc}. Retry in {retry}s.")
                time.sleep(retry)
        return False

    def _subscribe(self, initial: bool = False, extra: list[str] | None = None) -> None:
        topics = (extra or []) + (list(self._topic_handlers) if initial else [])
        for t in topics:
            try:
                res, _ = self._client.subscribe(t)
                if res == mqtt.MQTT_ERR_SUCCESS:
                    self._logger.debug(f"Subscribed to {t}")
                else:
                    self._logger.error(f"Subscribe error {res} for {t}")
            except Exception as exc:
                self._logger.error(f"Exception subscribing to {t}: {exc}")

    # ------------------------------------------------------------------ #
    # Callbacks                                                          #
    # ------------------------------------------------------------------ #
    def _on_connect(self, client, userdata, flags, reason, properties=None):
        if reason == 0:
            self._logger.info("MQTT CONNECTED")
            self._subscribe(initial=True)
        else:
            self._logger.error(f"MQTT connect failed rc={reason}")

    def _on_disconnect(self, client, userdata, flags, reason, properties=None):
        self._logger.warning(f"MQTT disconnected, reason={reason}")

    def _on_message(self, client, userdata, msg):
        handled = False
        for sub, cb in self._topic_handlers.items():
            if mqtt.topic_matches_sub(sub, msg.topic):
                handled = True
                try:
                    cb(msg.topic, msg.payload.decode())
                except Exception as exc:
                    self._logger.error(f"Handler error for {msg.topic}: {exc}")
        if not handled:
            self._logger.debug(f"Unhandled topic {msg.topic}")
