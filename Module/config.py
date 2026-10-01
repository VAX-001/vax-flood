# language: Python 3.10+, file: Module/config.py
# *attack profile + proxy pool persistence -- JSON round-trip, Output/ subdir*

import os, json, sys
from Module.colors  import R, Y, G, C, W, DG, RS
from Module.logger  import OUTPUT_DIR

CONFIG_PATH     = os.path.join(OUTPUT_DIR, "attack_profile.json")
PROXY_POOL_PATH = os.path.join(OUTPUT_DIR, "proxies_alive.json")

# ── attack profile ────────────────────────────────────────────────────
def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"{G}[+] Profile saved -> {CONFIG_PATH}{RS}")

def load_config() -> dict | None:
    if not os.path.exists(CONFIG_PATH):
        return None
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return None

# ── proxy pool ────────────────────────────────────────────────────────
def save_proxy_pool(proxies: list, path: str = "") -> None:
    dst = path or PROXY_POOL_PATH
    with open(dst, "w") as f:
        json.dump(proxies, f, indent=2)
    print(f"{G}[+] {len(proxies)} proxies saved -> {dst}{RS}")

def load_proxy_pool(path: str = "") -> list:
    src = path or PROXY_POOL_PATH
    if not os.path.exists(src):
        print(f"{R}[!] File not found: {src}{RS}")
        return []
    try:
        with open(src) as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("expected a JSON array")
        print(f"{G}[+] Loaded {len(data)} proxies from {src}{RS}")
        return data
    except Exception as e:
        print(f"{R}[!] Failed to load proxy pool: {e}{RS}")
        return []

# ── interactive helpers ───────────────────────────────────────────────
def ask(prompt: str, parser, default):
    """Prompt user, apply *parser*, return *default* on empty/invalid."""
    while True:
        try:
            v = input(prompt).strip()
            return parser(v) if v else default
        except Exception:
            print(f"{R}[!] Invalid input.{RS}")
