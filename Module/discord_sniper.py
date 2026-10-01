# language: Python 3.10+, file: Module/discord_sniper.py
# *Discord username sniper -- hammers unauthed constraints endpoint,*
# *token-bucket rate control, per-proxy sessions, live redraw display*
# entry: run_discord_sniper()

import asyncio, os, sys, time, random, string, itertools, datetime
from collections import deque

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import aiohttp

from Module.colors  import R, Y, G, C, W, DG, M, RS
from Module.config  import PROXY_POOL_PATH, load_proxy_pool
from Module.proxy   import fetch_proxies
from Module.http_flood import USER_AGENTS
from Module.logger  import OUTPUT_DIR

# ── constants ──────────────────────────────────────────────────────────
DISCORD_API       = "https://discord.com/api/v9/unique-username/username-attempt-unauthed"
SNIPER_CHARSET    = string.ascii_lowercase + string.digits + "_"
SNIPER_MIN        = 3
SNIPER_MAX        = 6
SNIPER_CONC       = 300          # concurrent worker tasks
SNIPER_RPS_DEF   = 50           # default target req/s
FOUND_PATH        = os.path.join(OUTPUT_DIR, "discord_found.txt")
_SNIPER_TIMEOUT   = aiohttp.ClientTimeout(total=4, connect=2)
_BLOCK_LINES      = 7           # 5 name rows + separator + stats = redraw block

# ── shared sniper state ────────────────────────────────────────────────
_found:      list  = []
_checked:    list  = [0]
_stop:       list  = [False]
_last_name:  list  = [""]
_rps:        list  = [SNIPER_RPS_DEF]
_disp_buf:   deque = deque(maxlen=5)   # (name, tag, color)
_disp_ready: list  = [False]
_bucket:     asyncio.Queue = None       # token bucket

# ── name generator ─────────────────────────────────────────────────────
def _name_gen(min_len=SNIPER_MIN, max_len=SNIPER_MAX):
    """Sequential product: aaa -> aab -> ... -> zzzzzz"""
    for length in range(min_len, max_len + 1):
        for combo in itertools.product(SNIPER_CHARSET, repeat=length):
            yield "".join(combo)

def _proxy_url(p: dict) -> str | None:
    if not p:
        return None
    return f"{p.get('protocol','http').lower()}://{p['ip']}:{p['port']}"

# ── check one name ────────────────────────────────────────────────────
async def _check(session: aiohttp.ClientSession, name: str, proxy_url) -> bool:
    _last_name[0] = name
    headers = {
        "User-Agent":       random.choice(USER_AGENTS),
        "Accept":           "application/json",
        "Content-Type":     "application/json",
        "Accept-Language":  "en-US,en;q=0.9",
        "Origin":           "https://discord.com",
        "Referer":          "https://discord.com/register",
        "X-Discord-Locale": "en-US",
        "X-Debug-Options":  "bugReporterEnabled",
    }
    payload = {"username": name}
    try:
        async with session.post(DISCORD_API, proxy=proxy_url, headers=headers,
                                json=payload, timeout=_SNIPER_TIMEOUT, ssl=False) as resp:
            _checked[0] += 1
            if resp.status == 200:
                data  = await resp.json()
                taken = data.get("taken", True)
                if not taken:
                    ts = datetime.datetime.now().strftime("%H:%M:%S")
                    _disp_buf.append((name, "FREE", G))
                    _found.append(name)
                    with open(FOUND_PATH, "a", encoding="utf-8") as f:
                        f.write(f"{name}\n")
                    return True
                else:
                    _disp_buf.append((name, "", R))
            elif resp.status == 429:
                retry = float(resp.headers.get("X-RateLimit-Reset-After", 5))
                _disp_buf.append((name, "429", Y))
                await asyncio.sleep(retry)
            else:
                _disp_buf.append((name, "", R))
    except Exception:
        _checked[0] += 1
        _disp_buf.append((name, "", R))
    return False

# ── token bucket refiller ──────────────────────────────────────────────
async def _refiller() -> None:
    """Drips exactly _rps[0] tokens per second into _bucket."""
    while not _stop[0]:
        rps      = max(1, _rps[0])
        interval = 1.0 / rps
        try:
            _bucket.put_nowait(1)
        except asyncio.QueueFull:
            pass
        await asyncio.sleep(interval)

# ── per-proxy worker ───────────────────────────────────────────────────
async def _worker(queue: asyncio.Queue, proxy_url) -> None:
    """Own TCPConnector per worker = keep-alive reuse, zero lock contention."""
    connector = aiohttp.TCPConnector(limit=4, ssl=False, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector,
                                     connector_owner=True) as session:
        while not _stop[0]:
            try:
                name = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                await asyncio.wait_for(_bucket.get(), timeout=2.0)
            except asyncio.TimeoutError:
                queue.task_done()
                continue
            await _check(session, name, proxy_url)
            queue.task_done()

# ── queue filler ───────────────────────────────────────────────────────
async def _fill(queue: asyncio.Queue, gen) -> None:
    for name in gen:
        if _stop[0]:
            break
        while queue.qsize() > SNIPER_CONC * 4:
            await asyncio.sleep(0.02)
        await queue.put(name)

# ── live stats display ─────────────────────────────────────────────────
async def _stats_display() -> None:
    """Redraws a fixed 7-line block in-place every 0.1s via ANSI cursor-up."""
    start    = time.time()
    last_cnt = 0
    last_5s  = 0.0
    rate5    = 0.0

    sys.stdout.write("\n" * _BLOCK_LINES)
    sys.stdout.flush()
    _disp_ready[0] = True

    while not _stop[0]:
        await asyncio.sleep(0.1)
        elapsed  = time.time() - start
        total    = _checked[0]
        rate_avg = total / elapsed if elapsed > 0 else 0.0

        if elapsed - last_5s >= 5:
            rate5    = (total - last_cnt) / max(elapsed - last_5s, 1)
            last_cnt = total
            last_5s  = elapsed

        rows = list(_disp_buf)
        while len(rows) < 5:
            rows.insert(0, ("", "", DG))

        out = [f"\033[{_BLOCK_LINES}A"]
        for name, tag, color in rows:
            if not name:
                out.append("\033[2K\n")
            elif tag == "FREE":
                out.append(f"\033[2K                   {G}★ {name:<12} <-- AVAILABLE!{RS}\n")
            elif tag == "429":
                out.append(f"\033[2K                   {Y}{name:<12} [rate-limit]{RS}\n")
            else:
                out.append(f"\033[2K                   {R}{name:<12}{RS}\n")

        out.append(f"\033[2K                   {DG}{'─' * 63}{RS}\n")
        fc = G if _found else DG
        out.append(
            f"\033[2K                   {C}[SNIPER]{RS} "
            f"checked={G}{total}{RS} "
            f"avg={G}{rate_avg:.0f}/s{RS} "
            f"5s={M}{rate5:.0f}/s{RS} "
            f"found={fc}{len(_found)}{RS} "
            f"t={C}{elapsed:.0f}s{RS}\n"
        )
        sys.stdout.write("".join(out))
        sys.stdout.flush()

# ── async runner ───────────────────────────────────────────────────────
async def _run(proxies: list, target_rps: int) -> None:
    global _bucket
    _rps[0]  = target_rps
    _bucket  = asyncio.Queue(maxsize=target_rps * 2)

    queue     = asyncio.Queue(maxsize=SNIPER_CONC * 8)
    gen       = _name_gen()
    proxy_urls = [_proxy_url(p) for p in proxies] if proxies else [None]

    workers = [
        asyncio.create_task(_worker(queue, proxy_urls[i % len(proxy_urls)]))
        for i in range(SNIPER_CONC)
    ]
    asyncio.create_task(_stats_display())
    asyncio.create_task(_refiller())

    try:
        await _fill(queue, gen)
        await queue.join()
    except asyncio.CancelledError:
        pass
    finally:
        _stop[0] = True
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

# ── public entry point ─────────────────────────────────────────────────
def run_discord_sniper() -> None:
    """Called from main menu [10]."""
    from Module.banner import cls, print_banner
    cls()
    print_banner()

    title_box = "DISCORD USERNAME SNIPER"
    print(f"                   {R}╔═══════════════════════════════════════════════════════════════╗{RS}")
    print(f"                   {R}║{RS}{W}{title_box:^63}{RS}{R}║{RS}")
    print(f"                   {R}║{RS}  Charset : {W}a-z  0-9  _{RS}                                          {R}║{RS}")
    print(f"                   {R}║{RS}  Length  : {W}{SNIPER_MIN} -> {SNIPER_MAX} chars{RS}                                       {R}║{RS}")
    print(f"                   {R}║{RS}  Workers : {W}{SNIPER_CONC:<4}{RS}                                                 {R}║{RS}")
    print(f"                   {R}║{RS}  Output  : {W}Output/discord_found.txt{RS}                               {R}║{RS}")
    print(f"                   {R}╚═══════════════════════════════════════════════════════════════╝{RS}\n")

    # speed selection
    print(f"{R}[{W}Speed{R}]{RS}  Target requests/second")
    print(f"  {R}[1]{RS}  10  rps  {DG}(safe){RS}")
    print(f"  {R}[2]{RS}  50  rps  {DG}(default){RS}")
    print(f"  {R}[3]{RS} 100  rps")
    print(f"  {R}[4]{RS} 250  rps")
    print(f"  {R}[5]{RS} 500  rps  {DG}(need 50+ good proxies){RS}")
    print(f"  {R}[c]{RS} Custom")
    _speed_map = {"1": 10, "2": 50, "3": 100, "4": 250, "5": 500}
    sc = input(f"{R}[{W}>{R}]{RS} Select [{W}2{RS}]: ").strip()
    if sc.lower() == "c":
        try:
            target_rps = max(1, min(int(input(f"{R}[{W}>{R}]{RS} Enter rps: ")), 5000))
        except ValueError:
            target_rps = SNIPER_RPS_DEF
    else:
        target_rps = _speed_map.get(sc, SNIPER_RPS_DEF)
    print(f"{G}[+] Speed set to {W}{target_rps}{G} req/s{RS}")

    # proxy source
    pool_exists = os.path.exists(PROXY_POOL_PATH)
    proxies: list = []
    print(f"\n{R}[{W}Proxy Source{R}]{RS}")
    print(f"  {R}[1]{RS} Use saved pool (proxies_alive.json)" if pool_exists
          else f"  {DG}[1] No saved pool found{RS}")
    print(f"  {R}[2]{RS} Fetch fresh proxies")
    print(f"  {R}[3]{RS} Run without proxies {DG}(risk: rate-limit fast){RS}")
    choice = input(f"{R}[{W}>{R}]{RS} Select [{W}1{RS}]: ").strip()

    if choice == "2":
        proxies = fetch_proxies()
    elif choice == "3" or (choice != "2" and not pool_exists):
        proxies = []
        print(f"{Y}[!] Running without proxies -- expect heavy rate-limiting{RS}")
    else:
        proxies = load_proxy_pool()
        if not proxies:
            print(f"{Y}[!] Pool empty, fetching fresh...{RS}")
            proxies = fetch_proxies()

    print(f"\n{G}[+] {len(proxies)} proxies loaded{RS}")
    print(f"{Y}[!] Sniper starting at {target_rps} rps in 3s... Ctrl+C to stop{RS}\n")
    time.sleep(3)

    # Clean screen and draw fresh banner right before starting live sniper display
    cls()
    print_banner()
    live_title = "DISCORD USERNAME SNIPER  •  LIVE"
    live_info  = f"Speed: {target_rps} req/s  |  Proxies: {len(proxies)}  |  Workers: {SNIPER_CONC}"
    print(f"                   {R}╔═══════════════════════════════════════════════════════════════╗{RS}")
    print(f"                   {R}║{RS}{W}{live_title:^63}{RS}{R}║{RS}")
    print(f"                   {R}║{RS}  {DG}{live_info:<59}{RS}  {R}║{RS}")
    print(f"                   {R}╚═══════════════════════════════════════════════════════════════╝{RS}")
    print()

    # reset state
    _stop[0]    = False
    _checked[0] = 0
    _last_name[0] = ""
    _found.clear()
    _disp_buf.clear()
    _disp_ready[0] = False

    try:
        asyncio.run(_run(proxies, target_rps))
    except KeyboardInterrupt:
        _stop[0] = True
        print(f"\n                   {Y}[!] Sniper stopped{RS}")

    print(f"\n                   {G}[DONE] Found {len(_found)} available name(s):{RS}")
    for n in _found:
        print(f"                   {G}  --> {W}{n}{RS}")
    if _found:
        print(f"                   {C}[*] Saved to Output/discord_found.txt{RS}")
    input(f"\n                   {DG}Press Enter to return to menu...{RS}")
