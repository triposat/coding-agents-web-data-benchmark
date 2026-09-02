"""Arm 5: the SAME naive request, from a US residential exit.

This is a raw residential proxy. No unblocking, no CAPTCHA handling, no
fingerprint management. The only thing that changes versus arm 1 is where the
packet leaves from, which is what isolates geography from everything else.
"""
import os, sys, json, time, urllib.request, urllib.error, ssl
sys.path.insert(0, "scripts")
from extract import classify

# export BD_PROXY="http://brd-customer-<id>-zone-<zone>:<password>@brd.superproxy.io:44445"
PROXY = os.environ["BD_PROXY"]
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}),
    urllib.request.HTTPSHandler(context=ctx))

skus = json.load(open("data/skus.json"))
TARGETS = [(s["sku_id"], s["product"], r, d["url"]) for s in skus for r, d in s["retailers"].items()]
rows = []
for sid, prod, ret, url in TARGETS:
    t0 = time.time(); st = None; body = ""; err = None
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"})
    try:
        with opener.open(req, timeout=45) as r:
            st = r.status; body = r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        st = e.code
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:110]}"
    outcome, fields = classify(st, body, err)
    row = {"arm": "arm5_us_residential", "sku_id": sid, "product": prod, "retailer": ret,
           "url": url, "http_status": st, "elapsed_s": round(time.time()-t0, 2),
           "bytes": len(body), "outcome": outcome, "error": err, **fields}
    open(f"data/payloads/arm5__{sid}__{ret}.txt", "w").write(body or "")
    rows.append(row)
    print(json.dumps({k: row[k] for k in ("sku_id","retailer","http_status","outcome","elapsed_s")}), flush=True)
    time.sleep(1)
json.dump(rows, open("data/arm5_us_residential.json", "w"), indent=2)
from collections import Counter
print("\n=== arm5 (US residential) ===", Counter(r["outcome"] for r in rows), file=sys.stderr)
