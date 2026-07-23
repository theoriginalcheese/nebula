"""Persistent log file so a silent pythonw run (no console attached) still
leaves a diagnosable trail, instead of activity/errors vanishing entirely.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from .paths import APP_DIR

LOG_DIR = os.path.join(APP_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "obsauto.log")

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
