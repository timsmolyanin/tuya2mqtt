import os
import enum
from dotenv import load_dotenv

load_dotenv()

# Tuya Cloud API credentials
API_KEY    = os.getenv("TUYA_API_KEY")
API_SECRET = os.getenv("TUYA_API_SECRET")
API_REGION = os.getenv("TUYA_API_REGION")

# MQTT Broker connection parameters
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT"))
MQTT_USERNAME    = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD    = os.getenv("MQTT_PASSWORD")

# UDP discovery ports
UDPPORT = 6666
UDPPORTS = 6667
UDPPORTAPP = 6669

# Service identifiers and prefixes
SERVICE_ID = "tuya2mqtt"
MQTT_TOPIC_PREFIX = "/devices"

# Service config files
DEVICES_CONF_FILE = os.getenv("TUYA2MQTT_DEV_CONF_FILE")
LOCAL_SCAN_FILE = os.getenv("TUYA2MQTT_LOCAL_SCAN_FILE")
EXTANSIONS_SETTINGS_FILE = os.getenv("TUYA2MQTT_EXTANSIONS_SETTINGS_FILE")

# Polling interval (seconds)
POLL_INTERVAL = float(os.getenv("TUYA2MQTT_POLL_INTERVAL"))

CONTROL = 7  # FRM_TP_CMD         # STATE_UPLOAD_CMD


class BridgeState(enum.Enum):
    OFFLINE   = 0
    LAN_ONLY  = 1
    ONLINE    = 2

# Supported Tuya device modes
TUYA_DEVICE_MODES = ("white", "colour", "scene", "music")

# Error codes
class ErrorStatus(enum.Enum):
    ERR_JSON        = "900" # Invalid JSON Response from Device
    ERR_CONNECT     = "901" # Network Error: Unable to Connect
    ERR_TIMEOUT     = "902" # Timeout Waiting for Device
    ERR_RANGE       = "903" # Specified Value Out of Range
    ERR_PAYLOAD     = "904" # Unexpected Payload from Device
    ERR_OFFLINE     = "905" # Network Error: Device Unreachable
    ERR_STATE       = "906" # Device in Unknown State
    ERR_FUNCTION    = "907" # Function Not Supported by Device
    ERR_DEVTYPE     = "908" # Device22 Detected: Retry Command
    ERR_CLOUDKEY    = "909" # Missing Tuya Cloud Key and Secret
    ERR_CLOUDRESP   = "910" # Invalid JSON Response from Cloud
    ERR_CLOUDTOKEN  = "911" # Unable to Get Cloud Token
    ERR_PARAMS      = "912" # Missing Function Parameters
    ERR_CLOUD       = "913" # Error Response from Tuya Cloud
    ERR_KEY_OR_VER  = "914" # Check device key or version

HRF_DP_TYPES = {
    "switch": {"type": "bool", "range": ["true", "false"]},
    "switch_led": {"type": "bool", "range": ["true", "false"]},
    "switch_led_1": {"type": "bool", "range": ["true", "false"]},
    "switch_1": {"type": "bool", "range": ["true", "false"]},
    "switch_2": {"type": "bool", "range": ["true", "false"]},
    "switch_3": {"type": "bool", "range": ["true", "false"]},
    "switch_4": {"type": "bool", "range": ["true", "false"]},
    "switch_5": {"type": "bool", "range": ["true", "false"]},
    "switch_6": {"type": "bool", "range": ["true", "false"]},
    "switch_7": {"type": "bool", "range": ["true", "false"]},
    "switch_8": {"type": "bool", "range": ["true", "false"]},
    "switch_9": {"type": "bool", "range": ["true", "false"]},
    "switch_10": {"type": "bool", "range": ["true", "false"]},
    "work_mode": {"type": "string", "range": ["white", "colour", "scene", "music"]},
    "bright_value": {"type": "int", "range": [0, 100]},
    "bright_value_v2": {"type": "int", "range": [0, 100]},
    "bright_value_1": {"type": "int", "range": [0, 100]},
    'brightness_min_1':{"type": "int", "range": [0, 100]},
    "temp_value": {"type": "int", "range": [0, 100]},
    "temp_value_v2": {"type": "int", "range": [0, 100]},
    "colour_data": {"type": "list", "range": [0, 100]},
    "colour_data_v2": {"type": "int", "range": [0, 100]},
    "relay_status": {"type": "string", "range": ["on", "off"]},
    "switch_inching": {"type": "string", "range": []},
    "scene_data": {},
    "countdown_1": {},
    "countdown": {},
    "music_data": {},
    "control_data": {}
}

# Types of Lightning devices refered to:
# https://developer.tuya.com/en/docs/iot/lighting?id=Kaiuyzxq30wmc
HRF_TUYA_DEVICE_CATEGORY = {
    "dj" : "Light",
    "dd": "Strip Lights",
    "dc": "String Lights",
    "fwd": "Ambiance Light",
    "xdd": "Ceiling Light",
    "gyd": "Motion Sensor Light",
    "fsd": "Ceiling Fat Light",
    "tyndg": "Solar Light",
    "tgq": "Dimmer",
    "sxd": "Spotlight",
    "ykq": "Remote Control",
    "kg": "Switch",
    "cz": "Socket",
    "pc": "Power Strip"
}


