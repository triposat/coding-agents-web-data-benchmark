import os
import re
from playwright.sync_api import sync_playwright
CDP = os.environ["BD_BROWSER_CDP"]  # wss://brd-customer-<id>-zone-<zone>:<pass>@brd.superproxy.io:9222
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp(CDP, timeout=180000)
    pg = b.new_page()
    pg.goto("https://www.bestbuy.com/site/searchpage.jsp?st=Sony+WH-1000XM5", timeout=180000, wait_until="domcontentloaded")
    pg.wait_for_timeout(5000)
    html = pg.content()
    open("data/bestbuy_search.html","w").write(html)
    print("bytes", len(html))
    print("TITLE:", (pg.title() or "")[:120])
    for pat in [r'skuId=(\d+)', r'/site/[^"]*?/(\d{7})\.p', r'data-sku-id="(\d+)"', r'"skuId":"?(\d{6,})', r'/product/[^"]+']:
        m = re.findall(pat, html)[:5]
        print(f"{pat!r:45} -> {m}")
    b.close()
