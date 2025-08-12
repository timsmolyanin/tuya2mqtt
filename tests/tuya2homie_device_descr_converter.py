
# -*- coding: utf-8 -*-

import json
import time

import sys

from core.tuya import tuya_constants as const
from core.utility_functions import *

from extensions.homie.common.homie_device_model import HomieDevice
from extensions.homie.common.homie_bridge_adapter import DeviceBridge
from extensions.homie.common.tuya_to_homie_converter import TuyaHomieConverter, TemplateManager
from extensions.homie.lifecycle.homie_lifecycle_extension import Extension as HomieLifecycleExtension
from core.settings_loader import load_settings

#------------------------------------
from core.logger_setup import configure_logger 
from core.device_repository import DeviceStore

from pprint import pprint


_logger = configure_logger()

# _config = load_settings("/home/tsmolyanin/wk/ttmp/tuya2mqtt/settings/config.toml")
_device_store = DeviceStore(_logger)

tuya_devices_conf = _device_store.read("/home/tsmolyanin/wk/smart-hub/tinytuya2mqtt/tests/devices_test.json")

if tuya_devices_conf:
    _device_store.load_devices(tuya_devices_conf)

_device_store.make_hum_name_to_id()

# pprint(tuya_devices_conf)

if tuya_devices_conf:
    _device_store.load_devices(tuya_devices_conf)

_device_store.make_hum_name_to_id()

_homie_converter = TuyaHomieConverter(TemplateManager("extensions/homie/common/templates/"))
test = _homie_converter.convert_device(_device_store.get_devices("bf633d4918dac89b96lpag").to_dict())
pprint(test)
# _sync = HomieLifecycleExtension(None, _device_store, _homie_converter, logger=_logger)
