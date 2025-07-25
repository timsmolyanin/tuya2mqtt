from dotenv import load_dotenv
from core.bridge_polling_loop import Tuya2MqttBridge

if __name__ == "__main__":
    load_dotenv('.env', override=True)
    bridge = Tuya2MqttBridge()
    bridge.start()
