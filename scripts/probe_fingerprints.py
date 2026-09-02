"""Capture what a server actually sees from each client used in this benchmark.

The post claims Best Buy refuses at the transport layer. That claim rests on error
strings. This measures the thing those strings are about: the TLS ClientHello (JA3/JA4)
and the HTTP/2 fingerprint Akamai's own paper describes, SETTINGS|WINDOW_UPDATE|
PRIORITY|header-order. No inference, just what the wire carries.
"""
import json, os, subprocess, sys
ECHO = "https://tls.peet.ws/api/all"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")
ARGS = ["--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--no-sandbox", "--disable-dev-shm-usage"]
STEALTH = """
Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
window.chrome = { runtime: {} };
"""
def summarise(raw, label):
    try:
        d = json.loads(raw)
    except Exception:
        return {"client": label, "error": str(raw)[:80]}
    t, h = d.get("tls", {}), d.get("http2", {})
    return {"client": label, "http": d.get("http_version"),
            "ja3_hash": t.get("ja3_hash"), "ja4": t.get("ja4"),
            "akamai_fp": h.get("akamai_fingerprint"),
            "akamai_hash": h.get("akamai_fingerprint_hash"),
            "ua": (d.get("user_agent") or "")[:52]}
out = []
# 1. plain python
import urllib.request
rq = urllib.request.Request(ECHO, headers={"User-Agent": UA})
out.append(summarise(urllib.request.urlopen(rq, timeout=30).read().decode(), "python urllib"))
# 2. curl
out.append(summarise(subprocess.run(["curl", "-s", "--max-time", "30", "-A", UA, ECHO],
                                    capture_output=True, text=True).stdout, "curl"))
# 3/4. headless chromium, default and hardened
from playwright.sync_api import sync_playwright
for label, hardened in (("chromium headless, default", False),
                        ("chromium headless, hardened", True)):
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=ARGS if hardened else [])
        ctx = b.new_context(user_agent=UA if hardened else None,
                            viewport={"width": 1440, "height": 900}, locale="en-US")
        if hardened: ctx.add_init_script(STEALTH)
        pg = ctx.new_page(); pg.goto(ECHO, timeout=60000, wait_until="domcontentloaded")
        out.append(summarise(pg.inner_text("body"), label)); b.close()
# 5. headful chromium, as close to a real browser as this machine gets
with sync_playwright() as p:
    b = p.chromium.launch(headless=False)
    pg = b.new_page(); pg.goto(ECHO, timeout=60000, wait_until="domcontentloaded")
    out.append(summarise(pg.inner_text("body"), "chromium headful")); b.close()
# 6. Bright Data Scraping Browser, if credentials are present
pw = os.environ.get("BD_SB_PW")
if pw:
    user = os.environ.get("BD_SB_USER", "")
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(f"wss://{user}:{pw}@brd.superproxy.io:9222", timeout=120000)
        pg = b.new_page(); pg.goto(ECHO, timeout=150000, wait_until="domcontentloaded")
        out.append(summarise(pg.inner_text("body"), "Bright Data Scraping Browser")); b.close()
json.dump(out, open("data/fingerprints.json", "w"), indent=2)
print(f"{'client':30} {'http':5} {'ja3_hash':34} {'akamai hash':34}")
for r in out:
    print(f"{r['client']:30} {str(r.get('http')):5} {str(r.get('ja3_hash')):34} {str(r.get('akamai_hash')):34}")
print()
for r in out:
    print(f"  {r['client']:30} akamai_fp = {r.get('akamai_fp')}")
