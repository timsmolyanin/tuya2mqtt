import logging

_LOG_FORMAT = "%(asctime)s [%(levelname)s] Tuya2MQTT: %(message)s"


def configure_logger(name: str = "Tuya2MQTT") -> logging.Logger:
    """
    Централизованная настройка логгера; повторные вызовы возвращают
    уже-сконфигурированный экземпляр, не плодя обработчики.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger               # Уже настроен
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logger.addHandler(handler)
    return logger
