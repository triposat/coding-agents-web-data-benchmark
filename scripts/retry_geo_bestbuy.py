"""Best Buy was excluded from the geography arm after 9 of 11 requests came back
502 from the proxy. That was one attempt with no retry and no session pinning,
which is not a fair test. This retries with a sticky session and backoff."""
import os, sys, json, time, ssl, random, urllib.request, urllib.error
sys.path.insert(0, "scripts")
from extract import classify

BASE = os.environ["BD_PROXY_BASE"]          # brd-customer-<id>-zone-<zone>
PW   = os.environ["BD_PROXY_PW"]
HOST = "brd.superproxy.io:44445"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE

def fetch(url, attempt):
    sess = f"-session-{random.randint(10**6,10**7)}"
    proxy = f"http://{BASE}-country-us{sess}:{PW}@{HOST}"
    op = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
        urllib.request.HTTPSHandler(context=ctx))
    req = urllib.request.Request(url, headers={"User-Agent": UA,
        "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language":"en-US,en;q=0.9"})
    try:
        with op.open(req, timeout=50) as r: return r.status, r.read().decode("utf-8","ignore"), None
    except urllib.error.HTTPError as e: return e.code, "", None
    except Exception as e: return None, "", f"{type(e).__name__}: {str(e)[:90]}"

skus=json.load(open("data/skus.json"))
targets=[(s["sku_id"], s["retailers"]["bestbuy"]["url"]) for s in skus if "bestbuy" in s["retailers"]]
rows=[]
for sid,url in targets:
    for attempt in range(1,4):
        st,body,err = fetch(url, attempt)
        if st == 502:
            time.sleep(2*attempt); continue
        break
    outcome,fields = classify(st, body, err)
    rows.append({"sku_id":sid,"retailer":"bestbuy","http_status":st,"attempts":attempt,
                 "bytes":len(body),"outcome":outcome,"error":err,**fields})
    print(json.dumps({k:rows[-1][k] for k in ("sku_id","http_status","attempts","outcome","bytes")}),flush=True)
    time.sleep(1)
json.dump(rows,open("data/arm5b_bestbuy_retry.json","w"),indent=2)
from collections import Counter
print("\n=== bestbuy, US exit, with retries ===", Counter(r["outcome"] for r in rows), file=sys.stderr)
