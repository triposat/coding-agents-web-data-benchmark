"""Do the discovered listing URLs actually resolve? Sample and fetch."""
import json, pathlib, random, urllib.request, urllib.error, ssl
from urllib.parse import urlparse
random.seed(7)
UA=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
KEYS=("new_listings","new_retailer_urls","listings","urls")
US = {"com","us"}

def urls(run):
    p=pathlib.Path(f"runs/{run}/new_listings.json")
    if not p.exists(): return []
    d=json.load(open(p)); rows=d if isinstance(d,list) else list(d.values())
    out=[]
    for r in rows:
        if not isinstance(r,dict): continue
        for c in next((r[k] for k in KEYS if k in r and r[k]),[]):
            u=c if isinstance(c,str) else (c.get("url") or "")
            if u: out.append(u)
    return out

res={}
for run in ("cursor_bd","claude_bd","claude_nobd_v2"):
    us=urls(run)
    if not us: res[run]={"sampled":0}; continue
    samp=random.sample(us,min(8,len(us)))
    ok=intl=0
    for u in samp:
        host=urlparse(u).netloc.replace("www.","")
        tld=host.rsplit(".",1)[-1]
        if tld not in US or host.endswith(".ca") or host.endswith(".co.uk"): intl+=1
        req=urllib.request.Request(u,headers={"User-Agent":UA})
        try:
            with urllib.request.urlopen(req,timeout=25,context=ctx) as r:
                ok += (r.status==200 and len(r.read(2000))>500)
        except Exception: pass
    # count non-.com across the FULL set, not just the sample
    hosts=[urlparse(u).netloc.replace("www.","") for u in us]
    nonus=sum(1 for h in hosts if h.rsplit(".",1)[-1] not in US)
    res[run]={"total":len(us),"sampled":len(samp),"resolved_200":ok,
              "non_us_tld_full_set":nonus,"non_us_pct":round(100*nonus/len(us))}
    print(f"{run:18} n={len(us):3}  sample {ok}/{len(samp)} resolved   non-US TLDs {nonus}/{len(us)} ({res[run]['non_us_pct']}%)")
json.dump(res,open("data/new_listings_live.json","w"),indent=2)
