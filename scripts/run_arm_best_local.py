"""Arm 2c: the best local setup we can build. Hardened headless Chromium routed
through a US residential exit. This is the fair opponent: both cheap fixes
applied at once, so the remaining gap is what a data layer actually sells."""
import os, sys, json, time
sys.path.insert(0, "scripts")
from extract import classify
from playwright.sync_api import sync_playwright

BASE=os.environ["BD_PROXY_BASE"]; PW=os.environ["BD_PROXY_PW"]
UA=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")
ARGS=["--disable-blink-features=AutomationControlled","--no-sandbox","--disable-dev-shm-usage"]
STEALTH="""Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
window.chrome={runtime:{}};"""

skus=json.load(open("data/skus.json"))
TARGETS=[(s["sku_id"],r,d["url"]) for s in skus for r,d in s["retailers"].items()]
rows=[]
with sync_playwright() as pw:
    br=pw.chromium.launch(headless=True,args=ARGS,
        proxy={"server":"http://brd.superproxy.io:44445",
               "username":f"{BASE}-country-us","password":PW})
    for sid,ret,url in TARGETS:
        t0=time.time(); st=None; body=""; err=None
        try:
            ctx=br.new_context(user_agent=UA,locale="en-US",
                viewport={"width":1440,"height":900},timezone_id="America/New_York",
                ignore_https_errors=True,
                extra_http_headers={"Accept-Language":"en-US,en;q=0.9"})
            ctx.add_init_script(STEALTH)
            pg=ctx.new_page()
            resp=pg.goto(url,timeout=60000,wait_until="domcontentloaded")
            pg.wait_for_timeout(3000)
            st=resp.status if resp else None; body=pg.content(); ctx.close()
        except Exception as e:
            err=f"{type(e).__name__}: {str(e)[:100]}"
        outcome,fields=classify(st,body,err)
        rows.append({"arm":"arm2c_best_local","sku_id":sid,"retailer":ret,"http_status":st,
                     "elapsed_s":round(time.time()-t0,2),"bytes":len(body),
                     "outcome":outcome,"error":err,**fields})
        print(json.dumps({k:rows[-1][k] for k in ("sku_id","retailer","outcome","elapsed_s")}),flush=True)
        time.sleep(1)
    br.close()
json.dump(rows,open("data/arm2c_best_local.json","w"),indent=2)
from collections import Counter
print("\n=== arm2c best local ===",Counter(r["outcome"] for r in rows),file=sys.stderr)
