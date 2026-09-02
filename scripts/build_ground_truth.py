import os
"""Ground truth for field accuracy.

Captured with the Bright Data SCRAPING BROWSER (full rendered DOM), which is a
different product and a different code path from arm 3's scrape_as_markdown.
That avoids scoring an arm against itself. A random sample is then hand-checked
against the saved HTML, and the hand-check result is reported alongside.
"""
import sys, json, time, re
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "scripts")
from playwright.sync_api import sync_playwright
from extract import availability_of, first, PRICE_RX, RATING_RX

CDP = os.environ["BD_BROWSER_CDP"]  # wss://brd-customer-<id>-zone-<zone>:<pass>@brd.superproxy.io:9222
skus = json.load(open("data/skus.json"))
TARGETS = [(s["sku_id"], s["product"], r, d["url"])
           for s in skus for r, d in s["retailers"].items()]

def grab(args):
    sid, prod, ret, url = args
    rec = {"sku_id": sid, "product": prod, "retailer": ret, "url": url}
    for attempt in (1, 2):
        try:
            with sync_playwright() as p:
                b = p.chromium.connect_over_cdp(CDP, timeout=180000)
                pg = b.new_page()
                pg.goto(url, timeout=180000, wait_until="domcontentloaded")
                pg.wait_for_timeout(4000)
                html = pg.content()
                title = pg.title() or ""
                b.close()
            open(f"data/payloads/gt__{sid}__{ret}.html", "w").write(html)
            txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S|re.I)
            txt = re.sub(r"<[^>]+>", " ", txt)
            rec.update(name=title.strip()[:200] or None,
                       price=first(PRICE_RX, html),
                       rating=first(RATING_RX, html),
                       availability=availability_of(txt),
                       html_bytes=len(html), ok=True)
            return rec
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {str(e)[:120]}"
            time.sleep(5)
    rec["ok"] = False
    return rec

with ThreadPoolExecutor(max_workers=4) as ex:      # low concurrency: bucket_rate_limit fired at 10
    rows = list(ex.map(grab, TARGETS))
json.dump(rows, open("data/ground_truth.json", "w"), indent=2)
ok = sum(1 for r in rows if r.get("ok"))
full = sum(1 for r in rows if all(r.get(f) for f in ("name","price","rating","availability")))
print(f"captured {ok}/{len(rows)} pages; all four fields present on {full}")
