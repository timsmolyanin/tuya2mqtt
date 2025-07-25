import sys
import adapters.tiny_cloud as tinytuya
import requests.exceptions as req_exc
import const


class CloudAPI:
    """
    Тонкая обёртка над tinytuya.Cloud:
    • следит за наличием учётных данных,
    • умеет переинициализироваться при потере соединения.
    """

    def __init__(self, logger):
        self._logger = logger
        self._cloud = None
        self._init_cloud()

    def _init_cloud(self):
        if not all((const.API_KEY, const.API_SECRET, const.API_REGION)):
            self._logger.critical("Нет учётных данных Tuya Cloud в .env")
            sys.exit(1)
        try:
            self._cloud = tinytuya.Cloud(
                apiKey=const.API_KEY,
                apiSecret=const.API_SECRET,
                apiRegion=const.API_REGION,
                apiDeviceID="",
                new_sign_algorithm=True,
            )
            if self._cloud.error:
                err = self._cloud.error.get("Payload", "Unknown error")
                self._logger.error(f"Cloud init error: {err}")
                self._cloud = None
        except req_exc.ConnectionError as exc:
            # There we should set a flag, that we don't have internet connection
            # so we cant add or update device, but we cant poll devices if we have local network
            self._logger.warning(f"Cloud init failed (no Internet): {exc}")
            self._cloud = None
        except Exception as exc:
            self._logger.error(f"Unexpected Cloud init error: {exc}")
            self._cloud = None
    
    def tuya_cloud_request(self):
        tuya_cloud_answer = {}
        try:
            tuya_cloud_answer = self._cloud.getdevices(verbose=False, include_map=True)
            return tuya_cloud_answer
        except Exception as e:
            self._logger.error(f"Exception calling cloud.getdevices: {e}")
            return
    
    def is_cloud_init(self):
        if self._cloud is None:
            self._init_cloud()
        return self._cloud

    def set_device_id(self, dev_id: list):
        self._cloud.set_device_id(dev_id)
