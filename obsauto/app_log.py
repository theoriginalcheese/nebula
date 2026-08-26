"""Persistent log file so a silent pythonw run (no console attached) still
leaves a diagnosable trail, instead of activity/errors vanishing entirely.
"""

import logging
import os
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler

from .paths import APP_DIR

LOG_DIR = os.path.join(APP_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "obsauto.log")
NATIVE_CRASH_FILE = os.path.join(LOG_DIR, "crash-native.log")

_logger = None


def setup_logging():
    global _logger
    if _logger is not None:
        return _logger

    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("obsauto")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)
    _logger = logger
    return logger


def log_to_file(message):
    if _logger is not None:
        _logger.info(message)


_hooks_installed = False


def install_excepthooks():
    """Route uncaught exceptions into the app log.

    The legacy Tk shell routed callback exceptions via
    ``report_callback_exception`` (gui.py), but the shipping v4 WebView UI has
    no Tk root - so under pythonw a crash on the main thread
    (``sys.excepthook``) or in any worker / JS-bridge thread
    (``threading.excepthook``) printed to a stderr that does not exist and
    vanished. This installs both hooks once; existing hooks are chained, not
    replaced. Also enables faulthandler for native crashes (access violations
    from the WinForms / WebView2 interop layer) - those kill the process
    before any Python hook can run, so they get their own file.
    """
    global _hooks_installed
    if _hooks_installed:
        return
    _hooks_installed = True

    logger = setup_logging()
    prev_sys_hook = sys.excepthook
    prev_thread_hook = threading.excepthook

    def _fmt(exc_type, exc_value, exc_tb):
        return "".join(traceback.format_exception(exc_type, exc_value,
                                                  exc_tb)).rstrip()

    def _sys_hook(exc_type, exc_value, exc_tb):
        try:
            logger.critical("Uncaught exception (main thread):\n%s",
                            _fmt(exc_type, exc_value, exc_tb))
        finally:
            if prev_sys_hook is not None:
                prev_sys_hook(exc_type, exc_value, exc_tb)

    def _thread_hook(args):
        try:
            name = args.thread.name if args.thread is not None else "?"
            logger.critical("Uncaught exception (thread %s):\n%s", name,
                            _fmt(args.exc_type, args.exc_value,
                                 args.exc_traceback))
        finally:
            if prev_thread_hook is not None:
                prev_thread_hook(args)

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook

    try:
        import faulthandler
        if not faulthandler.is_enabled():
            os.makedirs(LOG_DIR, exist_ok=True)
            fh = open(NATIVE_CRASH_FILE, "a", encoding="utf-8")
            faulthandler.enable(file=fh)
            # fh stays open deliberately: faulthandler needs the handle for
            # the life of the process, and the process is our cleanup.
    except Exception:  # pragma: no cover - faulthandler is best-effort
        pass
