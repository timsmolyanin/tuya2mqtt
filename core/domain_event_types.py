from dataclasses import dataclass

@dataclass
class StatusPolled:
    dev_id: str
    dps: dict

@dataclass
class MqttCommand:
    topic: str
    payload: str
