import os
"""Verify the Bright Data Scraping Browser arm end to end over CDP."""
import time, json
from playwright.sync_api import sync_playwright

CDP = os.environ["BD_BROWSER_CDP"]  # wss://brd-customer-<id>-zone-<zone>:<pass>@brd.superproxy.io:9222
URLS = [
    ("bestbuy", "https://www.bestbuy.com/site/apple-airpods-pro-2/6447382.p?skuId=6447382"),
    ("ebay",    "https://www.ebay.com/itm/335581646339"),
    ("newegg",  "https://www.newegg.com/p/N82E16824012039"),
]
out = []
with sync_playwright() as p:
    for name, url in URLS:
        rec = {"retailer": name, "url": url}
        t0 = time.time()
        try:
            b = p.chromium.connect_over_cdp(CDP, timeout=120000)
            pg = b.new_page()
            resp = pg.goto(url, timeout=120000, wait_until="domcontentloaded")
            pg.wait_for_timeout(3000)
            html = pg.content()
            rec.update(status=resp.status if resp else None, bytes=len(html),
                       title=(pg.title() or "")[:120], elapsed=round(time.time()-t0, 2))
            b.close()
        except Exception as e:
            rec.update(status=None, error=f"{type(e).__name__}: {str(e)[:200]}",
                       elapsed=round(time.time()-t0, 2))
        out.append(rec); print(json.dumps(rec), flush=True)
json.dump(out, open("data/sb_test.json", "w"), indent=2)
