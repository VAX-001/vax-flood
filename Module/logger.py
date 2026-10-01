# language: Python 3.10+, file: Module/logger.py
# *file logger + log_event() helper -- configured once at import time*

import os, logging

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(_BASE, "Output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

LOG_PATH = os.path.join(OUTPUT_DIR, "attack_log.txt")

logging.basicConfig(
    filename  = LOG_PATH,
    level     = logging.INFO,
    format    = "%(asctime)s | %(levelname)s | %(message)s",
    datefmt   = "%Y-%m-%d %H:%M:%S",
    encoding  = "utf-8",
)
_log = logging.getLogger("vax-flood")

def log_event(level: str, msg: str) -> None:
    """Fire a log record at *level* ('info', 'warning', 'error')."""
    getattr(_log, level, _log.info)(msg)
