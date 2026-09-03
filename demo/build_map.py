import json, re, os

TERMINAL_DIR = "/Users/triposat/.cursor/projects/Users-triposat-Desktop-Bdata-Cursor-bench-demo/agent-tools"

BATCHES = [
    ("9da1e05e-399f-4447-901c-b27a2dfb2b44.txt", "scraped/batch1"),
    ("19add6d7-b3c8-49d2-b7ab-6cdf72396b6e.txt", "scraped/batch2"),
    ("a8dfe612-7bd3-40a7-821f-c09ce73c275f.txt", "scraped/batch3"),
    ("4b6fda8a-8230-47d7-b8fe-caeba3569201.txt", "scraped/batch4"),
    ("95a8fb0f-7379-4bba-808a-53bee45bcdad.txt", "scraped/batch5"),
    ("1096c2d7-fd8b-49bb-940b-35789960ad14.txt", "scraped/batch6"),
    ("d4637e5f-7b7e-45f4-8ea7-7684c53fde06.txt", "scraped/batch7"),
]

def slugify(url):
    return re.sub(r'[^a-zA-Z0-9]+', '_', url)[:120]

url_map = {}

for term_file, outdir in BATCHES:
    path = os.path.join(TERMINAL_DIR, term_file)
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    data_line = None
    for line in lines:
        if line.strip().startswith('[{"url"'):
            data_line = line
            break
    data = json.loads(data_line)
    for item in data:
        url = item['url']
        content = item.get('content', '')
        fname = slugify(url) + '.md'
        fpath = os.path.join(outdir, fname)
        if len(content.strip()) == 0:
            url_map[url] = {"file": fpath, "failed": True}
        else:
            url_map[url] = {"file": fpath, "failed": False}

# Manual overrides for retried Best Buy pages fetched inline
url_map["https://www.bestbuy.com/product/bose-quietcomfort-ultra-2nd-gen-true-wireless-noise-cancelling-in-ear-earbuds-midnight-violet/J7C5V6WCWL/sku/12333019"] = {
    "file": "scraped/batch2_retry/bose_bestbuy.md", "failed": False
}
url_map["https://www.bestbuy.com/product/logitech-mx-master-3s-bluetooth-edition-performance-wireless-optical-mouse-with-ultra-fast-scrolling-and-quiet-clicks-wireless-black/J7H7ZYG559/sku/6633199"] = {
    "file": "scraped/batch2_retry/logitech_bestbuy.md", "failed": False
}
# Sony Best Buy page: 3 retries all returned empty (bot-blocked)
url_map["https://www.bestbuy.com/product/sony-wh-1000xm5-wireless-noise-cancelling-over-the-ear-headphones-black/J7XSRH5CXG/sku/10890357"] = {
    "file": None, "failed": True
}
# Walmart AirTag 4-pack (S03): scraper tool/MCP connection dropped before this URL could be fetched
url_map["https://www.walmart.com/ip/5395277557"] = {
    "file": None, "failed": True
}

with open('url_content_map.json', 'w') as f:
    json.dump(url_map, f, indent=2)

print(f"Mapped {len(url_map)} URLs")
for u, v in url_map.items():
    if v['failed']:
        print("FAILED:", u)
