"""The MCP server source exposes a GROUPS selector alongside PRO_MODE. The post
currently says you take 5 tools or all 74. If groups work on the hosted endpoint,
that is wrong and there is a middle tier."""
import json, os, urllib.request
import tiktoken
ENC = tiktoken.get_encoding("cl100k_base")
K = os.environ["BD_KEY"]
def enumerate_tools(qs):
    url = f"https://mcp.brightdata.com/mcp?token={K}{qs}"
    sess = {"id": None}; n = [0]
    def rpc(m, p=None, notify=False):
        n[0] += 1
        body = {"jsonrpc": "2.0", "method": m}
        if p is not None: body["params"] = p
        if not notify: body["id"] = n[0]
        rq = urllib.request.Request(url, data=json.dumps(body).encode())
        for k, v in (("Content-Type", "application/json"),
                     ("Accept", "application/json, text/event-stream"),
                     ("MCP-Protocol-Version", "2025-06-18")): rq.add_header(k, v)
        if sess["id"]: rq.add_header("Mcp-Session-Id", sess["id"])
        with urllib.request.urlopen(rq, timeout=90) as r:
            sid = r.headers.get("Mcp-Session-Id")
            if sid: sess["id"] = sid
            raw = r.read().decode("utf-8", "ignore")
        if notify: return None
        for ln in raw.splitlines():
            if ln.startswith("data: "): return json.loads(ln[6:])
        return json.loads(raw) if raw.strip() else None
    try:
        rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                           "clientInfo": {"name": "groups", "version": "1"}})
        rpc("notifications/initialized", {}, notify=True)
        tl = rpc("tools/list", {})
        tools = (tl.get("result") or {}).get("tools", [])
        return len(tools), len(ENC.encode(json.dumps(tools))), [t["name"] for t in tools]
    except Exception as e:
        return None, None, [f"{type(e).__name__}: {str(e)[:70]}"]

for label, qs in (("default", ""),
                  ("pro=1", "&pro=1"),
                  ("groups=ecommerce", "&groups=ecommerce"),
                  ("groups=e-commerce", "&groups=e-commerce"),
                  ("groups=ecommerce,advanced_scraping", "&groups=ecommerce,advanced_scraping")):
    n, tok, names = enumerate_tools(qs)
    if n is None:
        print(f"  {label:36} -> {names[0]}")
    else:
        wd = sum(1 for x in names if x.startswith("web_data_"))
        print(f"  {label:36} -> {n:>3} tools, {tok:>6,} tokens, {wd} web_data_*")
