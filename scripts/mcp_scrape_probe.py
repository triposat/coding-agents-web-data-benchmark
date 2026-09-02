"""Is scrape_as_markdown silently returning empty, or did BestBuy specifically fail?
Probe an easy site, a medium site, and hard retail targets."""
import sys, json, time; sys.path.insert(0, "scripts")
from mcp_client import rpc

URLS = [
    ("easy-example",  "https://example.com"),
    ("easy-httpbin",  "https://httpbin.org/html"),
    ("bd-own-site",   "https://brightdata.com/"),
    ("amazon",        "https://www.amazon.com/dp/B0D1XD1ZV3"),
    ("walmart",       "https://www.walmart.com/ip/5689919121"),
    ("bestbuy-new",   "https://www.bestbuy.com/product/sony-wh-1000xm6-best-wireless-noise-cancelling-headphones-black/J7XSRH5RCF/sku/6620467"),
    ("newegg",        "https://www.newegg.com/p/N82E16824012039"),
]
rows = []
for name, url in URLS:
    t0 = time.time()
    r = rpc("tools/call", {"name": "scrape_as_markdown", "arguments": {"url": url}})
    el = round(time.time() - t0, 1)
    res = (r or {}).get("result", {})
    content = res.get("content", [])
    text = content[0].get("text", "") if content else ""
    # strip the security wrapper to measure the ACTUAL payload
    payload = ""
    if "_BEGIN=====" in text and "_END=====" in text:
        payload = text.split("_BEGIN=====", 1)[1].rsplit("=====UNTRUSTED", 1)[0]
    row = {"target": name, "elapsed_s": el, "isError": res.get("isError"),
           "rpc_error": bool((r or {}).get("error")),
           "wrapped_len": len(text), "payload_len": len(payload.strip()),
           "payload_head": payload.strip()[:90].replace("\n", " ")}
    rows.append(row); print(json.dumps(row), flush=True)
json.dump(rows, open("data/mcp_scrape_probe.json", "w"), indent=2)
print("\nEMPTY PAYLOAD, NO ERROR:",
      sum(1 for r in rows if r["payload_len"] == 0 and not r["isError"] and not r["rpc_error"]),
      "/", len(rows))
