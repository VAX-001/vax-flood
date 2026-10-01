# language: Python 3.10+, file: Module/proxy.py
# *proxy fetch, async validator, interactive source picker*
# deps: pip install requests aiohttp aiohttp-socks

import asyncio, random, json, os, sys, requests
from Module.colors  import R, Y, G, C, W, DG, RS
from Module.state   import stats, slock
from Module.config  import save_proxy_pool, load_proxy_pool, PROXY_POOL_PATH

try:
    import aiohttp
    from aiohttp_socks import ProxyConnector, ProxyType
except ImportError:
    print("[!] aiohttp / aiohttp-socks not installed -- pip install aiohttp aiohttp-socks")

# ── upstream proxy sources (VAX-001 GitHub lists) ─────────────────────
PROXY_URLS: dict[str, str] = {
    "http":   "https://raw.githubusercontent.com/VAX-001/free-proxy/refs/heads/main/http.json",
    "https":  "https://raw.githubusercontent.com/VAX-001/free-proxy/refs/heads/main/https.json",
    "socks4": "https://raw.githubusercontent.com/VAX-001/free-proxy/refs/heads/main/socks4.json",
    "socks5": "https://raw.githubusercontent.com/VAX-001/free-proxy/refs/heads/main/socks5.json",
}

# ── fetch ─────────────────────────────────────────────────────────────
def fetch_proxies(proto_filter: list | None = None, verbose: bool = True) -> list:
    """Download proxy lists from upstream; optionally filter by protocol."""
    if verbose:
        print(f"{C}[*] Pulling proxy lists...{RS}")
    out: list = []
    for proto in (proto_filter or list(PROXY_URLS)):
        try:
            r = requests.get(PROXY_URLS[proto], timeout=20)
            r.raise_for_status()
            data = r.json()
            out.extend(data)
            if verbose:
                print(f"{G}  [+] {proto.upper()}: {len(data)} proxies{RS}")
        except Exception as e:
            if verbose:
                print(f"{R}  [-] {proto}: {e}{RS}")
    random.shuffle(out)
    return out

# ── async validator ───────────────────────────────────────────────────
async def _check_proxy(proxy: dict, sem: asyncio.Semaphore) -> dict | None:
    """Return proxy dict if live, None if dead."""
    ip, port = proxy["ip"], int(proxy["port"])
    pt = proxy.get("protocol", "http").lower()
    async with sem:
        try:
            if pt == "socks5":
                conn = ProxyConnector(proxy_type=ProxyType.SOCKS5, host=ip, port=port, rdns=True)
            elif pt == "socks4":
                conn = ProxyConnector(proxy_type=ProxyType.SOCKS4, host=ip, port=port)
            else:
                conn = ProxyConnector(proxy_type=ProxyType.HTTP,   host=ip, port=port)
            tm = aiohttp.ClientTimeout(total=3.0, connect=2.0)
            async with aiohttp.ClientSession(connector=conn, timeout=tm) as sess:
                async with sess.get("http://httpbin.org/ip", ssl=False, allow_redirects=False) as r:
                    if r.status < 600:
                        return proxy
        except Exception:
            return None

async def validate_proxies(proxies: list, batch: int = 200) -> list:
    """Concurrently validate *proxies*, render progress bar, return alive list."""
    print(f"{C}[*] Validating {len(proxies)} proxies (batch={batch})...{RS}")
    sem  = asyncio.Semaphore(batch)
    jobs = [_check_proxy(p, sem) for p in proxies]
    done, alive = 0, []
    for coro in asyncio.as_completed(jobs):
        res = await coro
        done += 1
        if res:
            alive.append(res)
        if done % 100 == 0 or done == len(proxies):
            pct = done * 100 // len(proxies)
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"\r{Y}  [{bar}] {done}/{len(proxies)} -- {G}{len(alive)} alive{RS}   ",
                  end="", flush=True)
    print()
    with slock:
        stats["proxies_total"] = len(proxies)
        stats["proxies_alive"] = len(alive)
    return alive

# ── connector factory ─────────────────────────────────────────────────
def make_connector(proxy: dict) -> "ProxyConnector":
    ip, port = proxy["ip"], int(proxy["port"])
    pt = proxy.get("protocol", "http").lower()
    if pt == "socks5":
        return ProxyConnector(proxy_type=ProxyType.SOCKS5, host=ip, port=port, rdns=True)
    if pt == "socks4":
        return ProxyConnector(proxy_type=ProxyType.SOCKS4, host=ip, port=port)
    return ProxyConnector(proxy_type=ProxyType.HTTP, host=ip, port=port)

# ── interactive picker ────────────────────────────────────────────────
def pick_proxy_source(pfilter: list | None, do_val: bool) -> list:
    """
    Interactive menu: fresh fetch / saved pool / merge / custom path.
    Validates if requested, auto-saves validated pool.
    Exits on empty result.
    """
    pool_exists = os.path.exists(PROXY_POOL_PATH)
    pool_size   = 0
    if pool_exists:
        try:
            with open(PROXY_POOL_PATH) as _f:
                pool_size = len(json.load(_f))
        except Exception:
            pool_exists = False

    print(f"\n{R}[{W}Proxy Source{R}]{RS}")
    print(f"  {R}[1]{RS} Fetch fresh from internet")
    if pool_exists:
        print(f"  {R}[2]{RS} Load saved pool  {DG}({pool_size} proxies -- proxies_alive.json){RS}")
        print(f"  {R}[3]{RS} Merge: fresh + saved")
    else:
        print(f"  {DG}[2] Load from file  (no pool yet -- validate first){RS}")
        print(f"  {DG}[3] Merge (unavailable){RS}")
    print(f"  {R}[4]{RS} Load from custom .json path")

    choice = input(f"{R}[{W}>{R}]{RS} Select [{W}1{RS}]: ").strip()
    proxies: list = []

    if choice == "4":
        custom  = input(f"{R}[{W}>{R}]{RS} Path to .json file: ").strip().strip('"').strip("'")
        proxies = load_proxy_pool(custom)
    elif choice == "2" and pool_exists:
        proxies = load_proxy_pool()
    elif choice == "3" and pool_exists:
        fresh = fetch_proxies(pfilter)
        saved = load_proxy_pool()
        seen, merged = set(), []
        for p in fresh + saved:
            key = f"{p.get('ip')}:{p.get('port')}"
            if key not in seen:
                seen.add(key)
                merged.append(p)
        random.shuffle(merged)
        proxies = merged
        print(f"{G}[+] Merged: {len(proxies)} unique proxies{RS}")
    else:
        proxies = fetch_proxies(pfilter)

    if not proxies:
        print(f"{R}[!] No proxies available. Aborting.{RS}")
        sys.exit(1)

    if do_val:
        proxies = asyncio.run(validate_proxies(proxies))
        if not proxies:
            print(f"{R}[!] All proxies dead after validation. Aborting.{RS}")
            sys.exit(1)
        save_proxy_pool(proxies)
    else:
        with slock:
            stats["proxies_total"] = len(proxies)
            stats["proxies_alive"] = len(proxies)

    return proxies
