import signal
import threading
import sys


class SignalManager:
    """Отвечает за graceful-shutdown при SIGINT/SIGTERM."""

    def __init__(self, shutdown_cb, logger):
        """
        :param shutdown_cb: функция, которую надо вызвать для выключения сервиса
        """
        self._shutdown_cb = shutdown_cb
        self._logger = logger

    def install(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle)

    def _handle(self, signum, _frame):
        # Start shutdown in daemon thread in order to do it from another context,
        # but not from context of signal-handler
        signame = signal.Signals(signum).name
        self._logger.info("Got %s — start gracefull shutdown", signame)
        th = threading.Thread(target=self._shutdown_and_exit, name="shutdown", daemon=True)
        th.start()

    def _shutdown_and_exit(self):
        try:
            self._shutdown_cb()
        finally:
            sys.exit(0)
