"""Quantify the intermittent silent-empty rate of scrape_as_markdown.
N repeated trials per target, same URL, recording payload length and latency."""
import sys, json, time; sys.path.insert(0, "scripts")
from mcp_client import rpc

N = 12
TARGETS = {
  "bestbuy": "https://www.bestbuy.com/product/sony-wh-1000xm6-best-wireless-noise-cancelling-headphones-black/J7XSRH5RCF/sku/6620467",
  "amazon":  "https://www.amazon.com/dp/B0D1XD1ZV3",
  "walmart": "https://www.walmart.com/ip/5689919121",
}
rows = []
for name, url in TARGETS.items():
    for i in range(N):
        t0 = time.time()
        try:
            r = rpc("tools/call", {"name": "scrape_as_markdown", "arguments": {"url": url}})
            res = (r or {}).get("result", {}); c = res.get("content", [])
            text = c[0].get("text", "") if c else ""
            payload = text.split("_BEGIN=====", 1)[1].rsplit("=====UNTRUSTED", 1)[0].strip() if "_BEGIN=====" in text else ""
            rows.append({"target": name, "trial": i, "elapsed_s": round(time.time()-t0, 1),
                         "payload_len": len(payload), "isError": res.get("isError"),
                         "empty_no_error": len(payload) == 0 and not res.get("isError")})
        except Exception as e:
            rows.append({"target": name, "trial": i, "elapsed_s": round(time.time()-t0, 1),
                         "payload_len": -1, "exception": f"{type(e).__name__}: {str(e)[:90]}"})
        print(json.dumps(rows[-1]), flush=True)
json.dump(rows, open("data/reliability_trials.json", "w"), indent=2)
print("\n=== SUMMARY ===")
for name in TARGETS:
    rs = [r for r in rows if r["target"] == name]
    empty = sum(1 for r in rs if r.get("empty_no_error"))
    lens = [r["payload_len"] for r in rs if r["payload_len"] > 0]
    lat = [r["elapsed_s"] for r in rs]
    print(f"{name:8} silent-empty {empty}/{len(rs)}  median_len={sorted(lens)[len(lens)//2] if lens else 0}"
          f"  lat p50={sorted(lat)[len(lat)//2]}s max={max(lat)}s")
