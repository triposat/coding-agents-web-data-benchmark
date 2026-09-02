"""Both sides at the same concurrency, which is how a price tracker actually runs.
Sequential baselines were hardened-local 21/41 and Bright Data 38/41. This asks
what happens to each when 41 pages are fetched 10 at a time from one machine."""
import json, os, sys, time, threading
sys.path.insert(0, os.path.dirname(__file__))
from concurrent.futures import ThreadPoolExecutor
from extract import classify
from mcp_client import rpc
from playwright.sync_api import sync_playwright

WORKERS = 10
HERE = os.path.dirname(__file__)
SKUS = json.load(open(os.path.join(HERE, "..", "data", "skus.json")))
TARGETS = [(s["sku_id"], r, d["url"]) for s in SKUS for r, d in s["retailers"].items()]
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")
ARGS = ["--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--no-sandbox", "--disable-dev-shm-usage"]
STEALTH = """
Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
window.chrome = { runtime: {} };
"""
lock = threading.Lock()

def local(t):
    sid, ret, url = t; t0 = time.time()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True, args=ARGS)
            ctx = b.new_context(user_agent=UA, viewport={"width":1440,"height":900},
                                locale="en-US")
            ctx.add_init_script(STEALTH)
            pg = ctx.new_page()
            r = pg.goto(url, timeout=60000, wait_until="domcontentloaded")
            pg.wait_for_timeout(2000)
            html = pg.content(); st = r.status if r else None
            oc, f = classify(st, html, None, is_markdown=False)
            b.close()
            return {"arm":"local_hardened_c10","sku_id":sid,"retailer":ret,"outcome":oc,
                    "bytes":len(html),"secs":round(time.time()-t0,1),**f}
    except Exception as e:
        oc, f = classify(None, "", f"{type(e).__name__}: {e}", is_markdown=False)
        return {"arm":"local_hardened_c10","sku_id":sid,"retailer":ret,"outcome":oc,
                "bytes":0,"secs":round(time.time()-t0,1),
                "err":f"{type(e).__name__}: {str(e)[:90]}"}

def bd(t):
    sid, ret, url = t; t0 = time.time(); body, err = "", None
    try:
        with lock:                      # mcp_client rpc is not thread-safe
            r = rpc("tools/call", {"name":"scrape_as_markdown","arguments":{"url":url}})
        res = (r or {}).get("result", {}); c = res.get("content", [])
        text = c[0].get("text","") if c else ""
        body = text.split("_BEGIN=====",1)[1].rsplit("=====UNTRUSTED",1)[0].strip() if "_BEGIN=====" in text else ""
        if (r or {}).get("error"): err = json.dumps(r["error"])[:150]
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:120]}"
    oc, f = classify(200 if body else None, body, err, is_markdown=True)
    if not body and not err: oc = "blocked_empty"
    return {"arm":"bd_c10","sku_id":sid,"retailer":ret,"outcome":oc,
            "bytes":len(body),"secs":round(time.time()-t0,1),**f}

for name, fn in (("local_hardened_c10", local), ("bd_c10", bd)):
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        rows = list(ex.map(fn, TARGETS))
    ok = sum(1 for r in rows if r["outcome"] == "success")
    json.dump(rows, open(os.path.join(HERE,"..","data",f"{name}.json"),"w"), indent=2)
    print(f"{name}: {ok}/{len(rows)} success in {round(time.time()-t0)}s wall", flush=True)
    from collections import Counter
    print("   ", Counter(r["outcome"] for r in rows), flush=True)
