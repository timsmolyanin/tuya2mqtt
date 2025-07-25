from abc import ABC, abstractmethod


class ILocalTransport(ABC):
    """Контракт (по-прежнему ABC), но без жёстких требований —
    базовые no-op-методы дают возможность наследнику *не* переопределять всё сразу."""

    # --- обязательные для TuyaDevice вызовы -----------------
    def status(self):               raise NotImplementedError
    def turn_on(self):              raise NotImplementedError
    def turn_off(self):             raise NotImplementedError
    def set_status(self, *_):       raise NotImplementedError
    def set_value(self, *_):        raise NotImplementedError
