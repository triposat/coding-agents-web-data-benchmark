"""Same URL, same zone, same session: HTML vs data_format=markdown.
Measures payload size and cl100k_base tokens, and whether each format still
carries the fields. Only same-URL pairs where BOTH succeeded are comparable."""
import json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(__file__))
from extract import classify
import tiktoken
ENC = tiktoken.get_encoding("cl100k_base")
K = os.environ["BD_KEY"]
HERE = os.path.dirname(__file__)
SKUS = json.load(open(os.path.join(HERE, "..", "data", "skus.json")))
OUT = os.path.join(HERE, "..", "data", "data_format_pairs.jsonl")

targets = [(r["sku_id"], ret, i["url"]) for r in SKUS for ret, i in r["retailers"].items()]

def call(url, markdown):
    body = {"zone": "web_unlocker", "url": url, "format": "json"}
    if markdown: body["data_format"] = "markdown"
    rq = urllib.request.Request("https://api.brightdata.com/request",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {K}", "Content-Type": "application/json"})
    t0 = time.time()
    try:
        d = json.loads(urllib.request.urlopen(rq, timeout=220).read())
        b = d.get("body", "") or ""
        oc, f = classify(d.get("status_code"), b, None, is_markdown=markdown)
        return {"status": d.get("status_code"), "bytes": len(b),
                "tokens": len(ENC.encode(b)) if b else 0, "outcome": oc,
                "name": bool(f.get("name")), "price": f.get("price"),
                "secs": round(time.time() - t0, 1)}
    except Exception as e:
        return {"status": "ERR", "bytes": 0, "tokens": 0, "outcome": "error",
                "err": f"{type(e).__name__}: {str(e)[:80]}", "secs": round(time.time() - t0, 1)}

def job(t):
    sku, ret, url = t
    rec = {"sku_id": sku, "retailer": ret, "url": url,
           "html": call(url, False), "markdown": call(url, True)}
    print(f"{sku:4} {ret:9} html {rec['html']['bytes']:>9,}b/{rec['html']['tokens']:>7,}t  "
          f"md {rec['markdown']['bytes']:>8,}b/{rec['markdown']['tokens']:>6,}t", flush=True)
    return rec

with ThreadPoolExecutor(max_workers=4) as ex, open(OUT, "w") as fh:
    for rec in ex.map(job, targets):
        fh.write(json.dumps(rec) + "\n"); fh.flush()
print("done", flush=True)
