"""Minimal MCP Streamable-HTTP client for the Bright Data MCP server.
Used to enumerate the exact tool surface an agent gets, and to call tools."""
import json, os, sys, urllib.request

KEY = os.environ["BD_KEY"]
URL = f"https://mcp.brightdata.com/mcp?token={KEY}"
_session = {"id": None}

def rpc(method, params=None, notify=False):
    body = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        body["params"] = params
    if not notify:
        body["id"] = 1
    req = urllib.request.Request(URL, data=json.dumps(body).encode())
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    req.add_header("MCP-Protocol-Version", "2025-06-18")
    if _session["id"]:
        req.add_header("Mcp-Session-Id", _session["id"])
    with urllib.request.urlopen(req, timeout=180) as r:
        sid = r.headers.get("Mcp-Session-Id")
        if sid:
            _session["id"] = sid
        raw = r.read().decode("utf-8", "ignore")
    if notify:
        return None
    for line in raw.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    return json.loads(raw) if raw.strip() else None

init = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                          "clientInfo": {"name": "bd-bench", "version": "1.0"}})
print("SERVER:", json.dumps(init.get("result", {}).get("serverInfo", {})))
print("SESSION:", _session["id"])
rpc("notifications/initialized", {}, notify=True)

tl = rpc("tools/list", {})
tools = tl.get("result", {}).get("tools", [])
print(f"\nTOOL COUNT: {len(tools)}\n")
for t in tools:
    req = t.get("inputSchema", {}).get("required", [])
    print(f"  - {t['name']:34} req={req}")
json.dump(tools, open("data/mcp_tools.json", "w"), indent=2)

if len(sys.argv) > 1 and sys.argv[1] == "call":
    res = rpc("tools/call", {"name": "search_engine",
                             "arguments": {"query": "airpods pro 2 price", "engine": "google"}})
    txt = json.dumps(res)[:1200]
    print("\nsearch_engine RESULT:", txt)

def call(name, args):
    import time
    t0 = time.time()
    r = rpc("tools/call", {"name": name, "arguments": args})
    el = round(time.time() - t0, 1)
    res = r.get("result", {}) if r else {}
    err = r.get("error") if r else None
    content = res.get("content", [])
    text = content[0].get("text", "") if content else ""
    print(f"\n=== {name} ({el}s) isError={res.get('isError')} rpcError={err}")
    print(text[:700] if text else json.dumps(r)[:700])
