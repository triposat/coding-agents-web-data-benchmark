"""Structured arm across every retailer with a dataset, scored the same way as
the fetch arms: a row counts only if a product name and a price are both present."""
import json, pathlib, collections
try:
    import tiktoken; enc=tiktoken.get_encoding("cl100k_base"); tok=lambda s: len(enc.encode(s))
except Exception: tok=lambda s: len(s)//4

skus=json.load(open("data/skus.json"))
url2={s["retailers"][r]["url"]:(s["sku_id"],r) for s in skus for r in s["retailers"]}
NAME=("title","product_name","name"); PRICE=("final_price","price","initial_price")
RAT=("rating","rating_stars"); AV=("availability","is_available","in_stock","available_for_delivery")

def pick(x,keys):
    for k in keys:
        if x.get(k) not in (None,"",[]): return x[k]
    return None

rows={}; blob=""
for r in ("amazon","walmart","target","bestbuy","newegg"):
    p=pathlib.Path(f"data/structured_{r}.json")
    if not p.exists(): continue
    d=json.load(open(p)); d=d if isinstance(d,list) else [d]; blob+=json.dumps(d)
    for x in d:
        u=str(x.get("url") or x.get("input",{}).get("url") or "")
        key=None
        for k,(sid,ret) in url2.items():
            if ret==r and (k==u or (k.split("/")[-1] and k.split("/")[-1] in u)):
                key=f"{sid}|{ret}"; break
        if key: rows[key]=x

a3={f"{x['sku_id']}|{x['retailer']}":x for x in json.load(open("data/arm3_brightdata_mcp.json"))}
a1={f"{x['sku_id']}|{x['retailer']}":x for x in json.load(open("data/arm1_plain_http.json"))}

print(f"{'retailer':10} {'pages':>6} {'structured':>11} {'BD markdown':>12} {'naive':>7}")
tot=collections.Counter()
for ret in ("amazon","walmart","target","bestbuy","newegg"):
    ks=[k for k in url2.values() if k[1]==ret]
    n=len(ks)
    st=sum(1 for k in rows if k.endswith("|"+ret) and pick(rows[k],NAME) and pick(rows[k],PRICE))
    md=sum(1 for k,v in a3.items() if k.endswith("|"+ret) and v["outcome"]=="success")
    nv=sum(1 for k,v in a1.items() if k.endswith("|"+ret) and v["outcome"]=="success")
    got=sum(1 for k in rows if k.endswith("|"+ret))
    tot["n"]+=n; tot["st"]+=st; tot["md"]+=md; tot["nv"]+=nv; tot["got"]+=got
    print(f"{ret:10} {n:>6} {str(st)+' /'+str(got):>11} {md:>12} {nv:>7}")
print(f"{'TOTAL':10} {tot['n']:>6} {str(tot['st'])+' /'+str(tot['got']):>11} {tot['md']:>12} {tot['nv']:>7}")
fields={f:sum(1 for x in rows.values() if pick(x,ks_)) for f,ks_ in
        (("name",NAME),("price",PRICE),("rating",RAT),("availability",AV))}
ident={f:sum(1 for x in rows.values() if x.get(f)) for f in ("upc","gtin","asin","sku","brand")}
print(f"\nrecords retrieved: {len(rows)}   fields: {fields}")
print(f"identifiers: {ident}")
print(f"structured payload tokens: {tok(blob):,}")
json.dump({"records":len(rows),"by_retailer_structured":tot['st'],"fields":fields,
           "identifiers":ident,"tokens":tok(blob)},open("data/structured_all.json","w"),indent=2)
