"""Arm 6: the structured web_data_* extractors, called through the MCP server in
pro mode. Same frozen URLs. This is the path we missed the first time by using
the server's default 5-tool profile."""
import os, sys, json, time, urllib.request
K=os.environ["BD_KEY"]; URL=f"https://mcp.brightdata.com/mcp?token={K}&pro=1"
_s={"id":None}
def rpc(m,p=None,notify=False):
    b={"jsonrpc":"2.0","method":m}
    if p is not None: b["params"]=p
    if not notify: b["id"]=1
    r=urllib.request.Request(URL,data=json.dumps(b).encode())
    for h,v in (("Content-Type","application/json"),("Accept","application/json, text/event-stream"),
                ("MCP-Protocol-Version","2025-06-18")): r.add_header(h,v)
    if _s["id"]: r.add_header("Mcp-Session-Id",_s["id"])
    with urllib.request.urlopen(r,timeout=180) as resp:
        sid=resp.headers.get("Mcp-Session-Id")
        if sid: _s["id"]=sid
        raw=resp.read().decode("utf-8","ignore")
    if notify: return None
    for line in raw.splitlines():
        if line.startswith("data: "): return json.loads(line[6:])
    return json.loads(raw) if raw.strip() else None

rpc("initialize",{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"bench","version":"1"}})
rpc("notifications/initialized",{},notify=True)

TOOL={"amazon":"web_data_amazon_product","walmart":"web_data_walmart_product",
      "bestbuy":"web_data_bestbuy_products"}
skus=json.load(open("data/skus.json"))
rows=[]
for s in skus:
    for ret,d in s["retailers"].items():
        if ret not in TOOL: continue
        t0=time.time(); payload=""; err=None
        try:
            r=rpc("tools/call",{"name":TOOL[ret],"arguments":{"url":d["url"]}})
            res=(r or {}).get("result",{}); c=res.get("content",[])
            txt=c[0].get("text","") if c else ""
            payload=txt.split("_BEGIN=====",1)[1].rsplit("=====UNTRUSTED",1)[0].strip() if "_BEGIN=====" in txt else txt
            if (r or {}).get("error"): err=json.dumps(r["error"])[:140]
        except Exception as e: err=f"{type(e).__name__}: {str(e)[:110]}"
        name=price=None
        try:
            j=json.loads(payload); j=j[0] if isinstance(j,list) and j else j
            if isinstance(j,dict):
                name=j.get("title") or j.get("product_name") or j.get("name")
                price=j.get("final_price") or j.get("price") or j.get("initial_price")
        except Exception: pass
        rows.append({"sku_id":s["sku_id"],"retailer":ret,"tool":TOOL[ret],
                     "elapsed_s":round(time.time()-t0,1),"chars":len(payload),
                     "name":name,"price":price,"ok":bool(name and price),"error":err})
        print(json.dumps({k:rows[-1][k] for k in ("sku_id","retailer","ok","chars","elapsed_s")}),flush=True)
json.dump(rows,open("data/arm6_mcp_pro.json","w"),indent=2)
import collections
print("\n=== arm6 web_data_* via MCP pro ===",
      dict(collections.Counter((r["retailer"], r["ok"]) for r in rows)), file=sys.stderr)
