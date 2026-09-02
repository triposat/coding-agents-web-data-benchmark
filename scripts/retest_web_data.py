"""Re-test the structured extractors properly.

Earlier attempts had two faults that were mine, not the product's: a 180s client
timeout on calls that trigger asynchronous collection jobs, and a field mapping I
guessed instead of reading. This gives each call 10 minutes, uses its own MCP
session per worker so nothing is serialised behind a lock, and discovers the price
field from the response rather than assuming its name.
"""
import json, os, re, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
K = os.environ["BD_KEY"]
URL = f"https://mcp.brightdata.com/mcp?token={K}&pro=1"
TOOL = {"amazon": "web_data_amazon_product", "walmart": "web_data_walmart_product",
        "bestbuy": "web_data_bestbuy_products"}
local = threading.local()
def rpc(method, params=None, notify=False):
    if not hasattr(local, "sid"): local.sid = None; local.n = 0
    local.n += 1
    body = {"jsonrpc": "2.0", "method": method}
    if params is not None: body["params"] = params
    if not notify: body["id"] = local.n
    rq = urllib.request.Request(URL, data=json.dumps(body).encode())
    for k, v in (("Content-Type", "application/json"),
                 ("Accept", "application/json, text/event-stream"),
                 ("MCP-Protocol-Version", "2025-06-18")): rq.add_header(k, v)
    if local.sid: rq.add_header("Mcp-Session-Id", local.sid)
    with urllib.request.urlopen(rq, timeout=600) as r:   # 10 minutes, not 3
        sid = r.headers.get("Mcp-Session-Id")
        if sid: local.sid = sid
        raw = r.read().decode("utf-8", "ignore")
    if notify: return None
    for ln in raw.splitlines():
        if ln.startswith("data: "): return json.loads(ln[6:])
    return json.loads(raw) if raw.strip() else None
def session():
    rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "retest", "version": "1"}})
    rpc("notifications/initialized", {}, notify=True)
def job(t):
    sku, ret, url = t
    if not hasattr(local, "ready"): session(); local.ready = True
    t0 = time.time()
    try:
        r = rpc("tools/call", {"name": TOOL[ret], "arguments": {"url": url}})
        c = (r.get("result") or {}).get("content") or []
        txt = c[0].get("text", "") if c else ""
        body = txt.split("_BEGIN=====", 1)[1].rsplit("=====UNTRUSTED", 1)[0].strip() if "_BEGIN=====" in txt else txt
        rec = None
        try:
            d = json.loads(body)
            rec = d[0] if isinstance(d, list) and d else (d if isinstance(d, dict) else None)
        except Exception: pass
        out = {"sku_id": sku, "retailer": ret, "secs": round(time.time()-t0,1),
               "chars": len(body), "record": rec,
               "err": json.dumps(r.get("error"))[:120] if r.get("error") else None}
    except Exception as e:
        out = {"sku_id": sku, "retailer": ret, "secs": round(time.time()-t0,1),
               "chars": 0, "record": None, "err": f"{type(e).__name__}: {str(e)[:100]}"}
    print(f"  {sku} {ret:8} {out['secs']:>6}s {out['chars']:>8} chars "
          f"{'record' if out['record'] else (out['err'] or 'no record')}", flush=True)
    return out
skus = json.load(open("data/skus.json"))
targets = [(s["sku_id"], r, i["url"]) for s in skus for r, i in s["retailers"].items() if r in TOOL]
with ThreadPoolExecutor(max_workers=4) as ex:
    rows = list(ex.map(job, targets))
json.dump(rows, open("data/web_data_retest.json", "w"), indent=2)
got = sum(1 for r in rows if r["record"])
print(f"\n  records returned: {got}/{len(rows)}")
