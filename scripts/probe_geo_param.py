"""Does search_engine's geo_location parameter change which domains come back?
The new-listings feed in an earlier run put 35% of its candidates on non-US
domains. This parameter was in the schema the whole time and we never passed it."""
import json, os, re, time, urllib.request, collections
KEY=os.environ["BD_KEY"]; URL=f"https://mcp.brightdata.com/mcp?token={KEY}&pro=1"
_s={"id":None}; _n=[0]
def rpc(m,p=None,notify=False):
    _n[0]+=1; body={"jsonrpc":"2.0","method":m}
    if p is not None: body["params"]=p
    if not notify: body["id"]=_n[0]
    rq=urllib.request.Request(URL,data=json.dumps(body).encode())
    for k,v in (("Content-Type","application/json"),("Accept","application/json, text/event-stream"),
                ("MCP-Protocol-Version","2025-06-18")): rq.add_header(k,v)
    if _s["id"]: rq.add_header("Mcp-Session-Id",_s["id"])
    with urllib.request.urlopen(rq,timeout=200) as r:
        sid=r.headers.get("Mcp-Session-Id")
        if sid: _s["id"]=sid
        raw=r.read().decode("utf-8","ignore")
    if notify: return None
    for ln in raw.splitlines():
        if ln.startswith("data: "): return json.loads(ln[6:])
    return json.loads(raw) if raw.strip() else None
rpc("initialize",{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"geo","version":"1"}})
rpc("notifications/initialized",{},notify=True)
NONUS=re.compile(r"\.(co\.uk|ca|in|de|fr|au|nl|it|es|com\.mx|com\.br)(/|$)")
PRODUCTS=["Anker 737 power bank 24000mAh","Sony WH-1000XM5 headphones","Logitech MX Master 3S mouse"]
for label,extra in (("no geo_location",{}),("geo_location=us",{"geo_location":"us"})):
    doms=collections.Counter(); nonus=0; tot=0
    for q in PRODUCTS:
        args={"query":f"{q} buy online"}; args.update(extra)
        r=rpc("tools/call",{"name":"search_engine","arguments":args})
        c=(r.get("result") or {}).get("content") or []
        txt=c[0].get("text","") if c else ""
        for u in re.findall(r'"link"\s*:\s*"(https?://[^"]+)"', txt):
            d=u.split("/")[2].replace("www.","")
            doms[d]+=1; tot+=1
            if NONUS.search(d): nonus+=1
        time.sleep(1)
    print(f"  {label:18} {tot:>3} results  non-US: {nonus:>2} ({nonus/tot*100 if tot else 0:.0f}%)")
    print(f"  {'':18} top: {dict(doms.most_common(5))}")
