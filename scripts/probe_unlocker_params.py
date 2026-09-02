"""Does Web Unlocker's country / data_format change the outcome on Best Buy,
the retailer no arm read reliably? Params we never passed in the benchmark."""
import json,os,sys,urllib.request,time
K=os.environ["BD_KEY"]
skus=json.load(open(os.path.join(os.path.dirname(__file__),"..","data","skus.json")))
bb=[(r['sku_id'],r['retailers']['bestbuy']['url']) for r in skus if 'bestbuy' in r['retailers']][:4]
def call(url, **kw):
    body={"zone":"web_unlocker","url":url,"format":"json"}; body.update(kw)
    rq=urllib.request.Request("https://api.brightdata.com/request",
        data=json.dumps(body).encode(),
        headers={"Authorization":f"Bearer {K}","Content-Type":"application/json"})
    t0=time.time()
    try:
        d=json.loads(urllib.request.urlopen(rq,timeout=200).read())
        b=d.get('body','') or ''
        return d.get('status_code'), len(b), ('$' in b), round(time.time()-t0,1), b[:70]
    except Exception as e:
        return 'ERR',0,False,round(time.time()-t0,1),f"{type(e).__name__}: {e}"[:70]
for cfg,kw in (("baseline",{}),("country=us",{"country":"us"}),
               ("country=us + data_format=markdown",{"country":"us","data_format":"markdown"})):
    print(f"\n  {cfg}",flush=True)
    for sku,u in bb:
        st,n,has,secs,snip=call(u,**kw)
        print(f"    {sku}  status={str(st):5} {n:>8,}b  has_$={has}  {secs:>6}s  {snip!r}"[:120],flush=True)
