"""Tools and parameters the MCP server exposes that we never used.
Found by reading the live tool schemas rather than the documentation."""
import json, os, time, urllib.request
KEY=os.environ["BD_KEY"]; URL=f"https://mcp.brightdata.com/mcp?token={KEY}&pro=1"
_s={"id":None}; _n=[0]
def rpc(method, params=None, notify=False):
    _n[0]+=1
    body={"jsonrpc":"2.0","method":method}
    if params is not None: body["params"]=params
    if not notify: body["id"]=_n[0]
    req=urllib.request.Request(URL, data=json.dumps(body).encode())
    req.add_header("Content-Type","application/json")
    req.add_header("Accept","application/json, text/event-stream")
    req.add_header("MCP-Protocol-Version","2025-06-18")
    if _s["id"]: req.add_header("Mcp-Session-Id",_s["id"])
    with urllib.request.urlopen(req, timeout=200) as r:
        sid=r.headers.get("Mcp-Session-Id")
        if sid: _s["id"]=sid
        raw=r.read().decode("utf-8","ignore")
    if notify: return None
    for ln in raw.splitlines():
        if ln.startswith("data: "): return json.loads(ln[6:])
    return json.loads(raw) if raw.strip() else None
rpc("initialize",{"protocolVersion":"2025-06-18","capabilities":{},
                  "clientInfo":{"name":"probe","version":"1"}})
rpc("notifications/initialized",{},notify=True)
def call(name,args):
    t0=time.time()
    try:
        r=rpc("tools/call",{"name":name,"arguments":args})
        if r.get("error"): return round(time.time()-t0,1),0,json.dumps(r["error"])[:220]
        c=(r.get("result") or {}).get("content") or []
        txt=c[0].get("text","") if c else json.dumps(r)[:300]
        return round(time.time()-t0,1),len(txt),txt
    except Exception as e:
        return round(time.time()-t0,1),0,f"{type(e).__name__}: {str(e)[:200]}"

for label,name,args in [
  ("session_stats (no args, never called)","session_stats",{}),
  ("discover (purpose-built for new listings)","discover",
     {"query":"Anker 737 power bank 24000mAh","intent":"find US online retailers selling this exact product",
      "country":"US","num_results":5,"remove_duplicates":True}),
  ("search_engine WITH geo_location","search_engine",
     {"query":"site:bestbuy.com anker 737 power bank","geo_location":"us"}),
]:
    s,n,t=call(name,args)
    print(f"\n=== {label} ===\n  {s}s  {n} chars\n  {t[:600]}")
