"""Build a VERIFIED fixed SKU list by searching each retailer's own site
through the Bright Data Scraping Browser. Records canonical product URLs
so every later run chases identical targets."""
import os, json, re, time, sys
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright

CDP = os.environ["BD_BROWSER_CDP"]  # wss://brd-customer-<id>-zone-<zone>:<pass>@brd.superproxy.io:9222

PRODUCTS = [
    "Apple AirPods Pro 2",
    "Sony WH-1000XM5 headphones",
    "Logitech MX Master 3S mouse",
    "Samsung T7 1TB portable SSD",
    "Anker 737 power bank",
    "Bose QuietComfort Ultra earbuds",
    "SanDisk Extreme Pro 1TB microSD",
    "Apple AirTag 4 pack",
    "Seagate 2TB external hard drive",
    "Razer DeathAdder V3 mouse",
]

SEARCH = {
    "amazon":  ("https://www.amazon.com/s?k={q}",            r"/dp/([A-Z0-9]{10})",        "https://www.amazon.com/dp/{id}"),
    "walmart": ("https://www.walmart.com/search?q={q}",      r"/ip/(?:[^/\"?]+/)?(\d{6,})", "https://www.walmart.com/ip/{id}"),
    "bestbuy": ("https://www.bestbuy.com/site/searchpage.jsp?st={q}", r"skuId=(\d{6,})",    "https://www.bestbuy.com/site/-/{id}.p?skuId={id}"),
    "target":  ("https://www.target.com/s?searchTerm={q}",   r"/p/[^\"]*?/-/A-(\d{6,})",   "https://www.target.com/p/-/A-{id}"),
    "newegg":  ("https://www.newegg.com/p/pl?d={q}",         r"/p/([A-Z0-9]{8,})",         "https://www.newegg.com/p/{id}"),
}

def find(args):
    retailer, product = args
    tmpl, pat, canon = SEARCH[retailer]
    q = product.replace(" ", "+")
    url = tmpl.format(q=q)
    rec = {"retailer": retailer, "product": product, "search_url": url}
    try:
        with sync_playwright() as p:
            b = p.chromium.connect_over_cdp(CDP, timeout=180000)
            pg = b.new_page()
            pg.goto(url, timeout=180000, wait_until="domcontentloaded")
            pg.wait_for_timeout(4000)
            html = pg.content()
            b.close()
        ids = re.findall(pat, html)
        ids = [i for i in ids if i]
        if ids:
            seen, uniq = set(), []
            for i in ids:
                if i not in seen:
                    seen.add(i); uniq.append(i)
            rec["product_id"] = uniq[0]
            rec["product_url"] = canon.format(id=uniq[0])
            rec["candidates"] = uniq[:5]
        else:
            rec["error"] = "no product id matched"
            rec["html_bytes"] = len(html)
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    print(json.dumps(rec), flush=True)
    return rec

jobs = [(r, p) for p in PRODUCTS for r in SEARCH]
with ThreadPoolExecutor(max_workers=10) as ex:
    results = list(ex.map(find, jobs))
json.dump(results, open("data/sku_discovery.json", "w"), indent=2)
ok = [r for r in results if r.get("product_url")]
print(f"\nRESOLVED {len(ok)}/{len(results)}", file=sys.stderr)
