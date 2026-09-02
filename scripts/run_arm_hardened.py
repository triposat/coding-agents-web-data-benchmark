"""Arm 2b: the headless browser, hardened the way a practitioner would.

Arm 2 launched Chromium with defaults, which is not a fair test of what a
competent engineer would ship. This applies the standard hardening the agents'
own generated trackers reached for: the automation blink flag off, the
webdriver property masked, a real viewport, and plausible client hints.
"""
import sys, json, time
sys.path.insert(0, "scripts")
from extract import classify
from playwright.sync_api import sync_playwright

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
const q = navigator.permissions.query;
navigator.permissions.query = (p) => p.name === 'notifications'
  ? Promise.resolve({state: Notification.permission}) : q(p);
"""

skus = json.load(open("data/skus.json"))
TARGETS = [(s["sku_id"], s["product"], r, d["url"]) for s in skus for r, d in s["retailers"].items()]
rows = []
with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=ARGS)
    for sid, prod, ret, url in TARGETS:
        t0 = time.time(); st = None; body = ""; err = None
        try:
            ctx = br.new_context(user_agent=UA, locale="en-US",
                                 viewport={"width": 1440, "height": 900},
                                 timezone_id="America/New_York",
                                 extra_http_headers={"Accept-Language": "en-US,en;q=0.9",
                                                     "Sec-CH-UA-Platform": '"macOS"'})
            ctx.add_init_script(STEALTH)
            pg = ctx.new_page()
            resp = pg.goto(url, timeout=45000, wait_until="domcontentloaded")
            pg.wait_for_timeout(3000)
            st = resp.status if resp else None
            body = pg.content()
            ctx.close()
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:110]}"
        outcome, fields = classify(st, body, err)
        open(f"data/payloads/arm2b__{sid}__{ret}.txt", "w").write(body or "")
        rows.append({"arm": "arm2b_hardened", "sku_id": sid, "retailer": ret, "url": url,
                     "http_status": st, "elapsed_s": round(time.time()-t0, 2),
                     "bytes": len(body), "outcome": outcome, "error": err, **fields})
        print(json.dumps({k: rows[-1][k] for k in ("sku_id","retailer","outcome","elapsed_s")}), flush=True)
        time.sleep(1)
    br.close()
json.dump(rows, open("data/arm2b_hardened.json", "w"), indent=2)
from collections import Counter
print("\n=== arm2b hardened ===", Counter(r["outcome"] for r in rows), file=sys.stderr)
