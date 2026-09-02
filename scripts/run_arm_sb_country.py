"""arm7: Bright Data Scraping Browser with -country-us on the CDP username,
against the full frozen SKU list. Tests whether geo-pinning the managed browser
changes the outcome, especially on Best Buy which no other arm read."""
import json, sys, time, os
sys.path.insert(0, os.path.dirname(__file__))
from extract import classify
from playwright.sync_api import sync_playwright

BASE = os.environ.get("BD_SB_USER", "brd-customer-<ID>-zone-<ZONE>")
PW   = os.environ["BD_SB_PW"]   # export before running; never commit this
SKUS = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "skus.json")))
OUT  = os.path.join(os.path.dirname(__file__), "..", "data", "arm7_sb_country.jsonl")

targets = []
for row in SKUS:
    for ret, info in row["retailers"].items():
        targets.append((row["sku_id"], ret, info["url"]))

done = set()
if os.path.exists(OUT):
    for ln in open(OUT):
        try: r = json.loads(ln); done.add((r["sku_id"], r["retailer"]))
        except Exception: pass

with open(OUT, "a") as fh:
    for sku, ret, url in targets:
        if (sku, ret) in done: continue
        t0 = time.time(); rec = {"sku_id": sku, "retailer": ret, "url": url}
        try:
            with sync_playwright() as p:
                b = p.chromium.connect_over_cdp(
                    f"wss://{BASE}-country-us:{PW}@brd.superproxy.io:9222", timeout=120000)
                pg = b.new_page()
                r = pg.goto(url, timeout=150000, wait_until="domcontentloaded")
                pg.wait_for_timeout(2500)
                html = pg.content()
                rec["status"] = r.status if r else None
                rec["bytes"] = len(html)
                oc, fields = classify(rec["status"], html, None, is_markdown=False)
                rec["outcome"] = oc; rec.update(fields)
                b.close()
        except Exception as e:
            rec["outcome"], rec["err"] = "error", f"{type(e).__name__}: {str(e)[:120]}"
        rec["secs"] = round(time.time() - t0, 1)
        fh.write(json.dumps(rec) + "\n"); fh.flush()
        print(f"{sku:4} {ret:9} {rec['outcome']:18} {rec['secs']:>6}s", flush=True)
