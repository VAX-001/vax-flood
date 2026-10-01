# language: Python 3.10+, file: Module/state.py
# *shared mutable state -- stats dict, locks, stop flags, ring buffers*
# *import as: from Module.state import stats, slock, stop, rps_buf*

import threading
from collections import deque

# ── attack stats ──────────────────────────────────────────────────────
stats: dict = {
    "sent":          0,
    "success":       0,
    "fail":          0,
    "dead":          0,
    "start":         0.0,
    "proxies_total": 0,
    "proxies_alive": 0,
    "bytes_sent":    0,
}

slock      = threading.Lock()
stop       = [False]           # [0] = True to signal all workers to halt
rps_buf    = deque(maxlen=10)  # rolling RPS samples for the printer thread
_last_sent = [0]               # previous tick's sent count -- used by printer

def reset_stats() -> None:
    """Wipe all counters before a new attack."""
    with slock:
        for k in stats:
            stats[k] = 0 if k != "start" else 0.0
        rps_buf.clear()
        _last_sent[0] = 0
    stop[0] = False
