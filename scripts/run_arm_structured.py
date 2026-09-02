"""Arm 4: Bright Data Web Scraper API, structured product records.

Same frozen URLs as every other arm. Returns typed JSON rather than markdown,
so there is no parsing step and no markdown token tax.
"""
import json, os, time, urllib.request, urllib.error

K = os.environ["BD_KEY"]
DATASETS = {"amazon": "gd_l7q7dkf244hwjntr0", "walmart": "gd_l95fol7l1ru6rlo116"}

def api(url, payload=None, method="GET"):
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(payload).encode() if payload else None)
    req.add_header("Authorization", f"Bearer {K}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())

skus = json.load(open("data/skus.json"))
out = {}
for retailer, ds in DATASETS.items():
    urls = [{"url": s["retailers"][retailer]["url"]} for s in skus if retailer in s["retailers"]]
    print(f"{retailer}: triggering {len(urls)} urls on {ds}", flush=True)
    try:
        t = api(f"https://api.brightdata.com/datasets/v3/trigger?dataset_id={ds}&include_errors=true", urls, "POST")
    except urllib.error.HTTPError as e:
        print("  trigger failed:", e.code, e.read()[:200].decode(errors="ignore")); continue
    sid = t.get("snapshot_id")
    print("  snapshot:", sid, flush=True)
    out[retailer] = {"snapshot_id": sid, "dataset_id": ds, "n_urls": len(urls)}
json.dump(out, open("data/structured_snapshots.json", "w"), indent=2)
print(json.dumps(out, indent=2))
