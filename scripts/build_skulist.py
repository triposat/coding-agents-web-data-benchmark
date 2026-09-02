"""Lock the fixed SKU list. Uses MCP search_engine with site: queries, then
validates each candidate URL against that retailer's product-URL pattern.
Output data/skus.json is the frozen target list for every later run."""
import sys, json, re, time; sys.path.insert(0, "scripts")
from mcp_client import rpc

PRODUCTS = [
    "Apple AirPods Pro 2", "Sony WH-1000XM5 wireless headphones",
    "Logitech MX Master 3S mouse", "Samsung T7 1TB portable SSD",
    "Anker 737 power bank 24000mAh", "Bose QuietComfort Ultra earbuds",
    "SanDisk Extreme Pro 1TB microSDXC", "Apple AirTag 4 pack",
    "Seagate Expansion 2TB external hard drive", "Razer DeathAdder V3 mouse",
]
# retailer -> (search domain, regex that identifies a PRODUCT url, normaliser)
PAT = {
  "amazon":  ("amazon.com",  re.compile(r"https://www\.amazon\.com/(?:[^/\s\"]+/)?dp/([A-Z0-9]{10})")),
  "walmart": ("walmart.com", re.compile(r"https://www\.walmart\.com/ip/(?:[^/\s\"?]+/)?(\d{6,})")),
  "bestbuy": ("bestbuy.com", re.compile(r"https://www\.bestbuy\.com/product/[^\s\"?]+/sku/(\d{6,})")),
  "target":  ("target.com",  re.compile(r"https://www\.target\.com/p/[^\s\"?]*?/-/A-(\d{6,})")),
  "newegg":  ("newegg.com",  re.compile(r"https://www\.newegg\.com/[^\s\"?]*?/p/([A-Z0-9]{8,})")),
}
CANON = {
  "amazon":  "https://www.amazon.com/dp/{id}",
  "walmart": "https://www.walmart.com/ip/{id}",
  "bestbuy": None,   # keep full url, slug is load-bearing
  "target":  "https://www.target.com/p/-/A-{id}",
  "newegg":  None,
}

def extract(text):
    if "_BEGIN=====" in text:
        return text.split("_BEGIN=====", 1)[1].rsplit("=====UNTRUSTED", 1)[0]
    return text

rows = []
for retailer, (domain, rx) in PAT.items():
    for chunk_start in range(0, len(PRODUCTS), 10):
        chunk = PRODUCTS[chunk_start:chunk_start+10]
        queries = [{"query": f'site:{domain} {p}', "engine": "google", "geo_location": "us"} for p in chunk]
        t0 = time.time()
        r = rpc("tools/call", {"name": "search_engine_batch", "arguments": {"queries": queries}})
        res = (r or {}).get("result", {}); c = res.get("content", [])
        blob = extract(c[0].get("text", "")) if c else ""
        print(f"[{retailer}] batch of {len(chunk)} in {round(time.time()-t0,1)}s, {len(blob)} chars", flush=True)
        # the batch returns one blob; split per query by locating each product's own result set
        for p in chunk:
            # search the whole blob, take first URL matching this retailer's product pattern
            # near the product's own query block if identifiable, else global first
            m = rx.search(blob)
            rows.append({"retailer": retailer, "product": p,
                         "blob_len": len(blob), "found": bool(m)})
        # keep raw for precise per-query parsing
        open(f"data/serp_{retailer}_{chunk_start}.json", "w").write(blob)
print("\nwrote raw SERP blobs; parsing per-query next")
