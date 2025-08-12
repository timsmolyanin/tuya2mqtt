"""Tests for TuyaHomieConverter handling of devices without templates."""

from extensions.homie.common.tuya_to_homie_converter import (
    TemplateManager,
    TuyaHomieConverter,
)


def test_convert_device_without_template():
    converter = TuyaHomieConverter(
        TemplateManager("extensions/homie/common/templates/")
    )

    device = {
        "id": "dummy123",
        "name": "Dummy",
        "mapping": {
            "1": {"code": "switch", "type": "Boolean"}
        },
    }

    dev_id, desc, mapping, strict = converter.convert_device(device)

    assert dev_id == "dummy123"
    assert mapping is None
    assert strict is False
    assert desc["name"] == "Dummy"
