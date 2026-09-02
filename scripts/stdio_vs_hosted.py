import json, subprocess, os, threading, time, sys
sys.path.insert(0, "scripts")
KEY = os.environ["BD_KEY"]
URL = "https://example.com"

# ---- LOCAL stdio, capturing stderr ----
env = dict(os.environ, API_TOKEN=KEY)
p = subprocess.Popen(["mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE, env=env, text=True, bufsize=1)
errlines = []
threading.Thread(target=lambda: [errlines.append(l) for l in p.stderr], daemon=True).start()
out = {}
def send(o): p.stdin.write(json.dumps(o)+"\n"); p.stdin.flush()
def rd():
    for line in p.stdout:
        try: m = json.loads(line)
        except Exception: continue
        if m.get("id") == 3: out["res"] = m; return
t = threading.Thread(target=rd, daemon=True); t.start()
send({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"p","version":"1"}}})
send({"jsonrpc":"2.0","method":"notifications/initialized","params":{}})
time.sleep(3)
t0=time.time(); send({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"scrape_as_markdown","arguments":{"url":URL}}})
t.join(timeout=120); el=round(time.time()-t0,1); p.kill()
r = out.get("res", {}); res = (r or {}).get("result", {}) or {}
c = res.get("content", []); txt = c[0].get("text","") if c else ""
pay = txt.split("_BEGIN=====",1)[1].rsplit("=====UNTRUSTED",1)[0].strip() if "_BEGIN=====" in txt else txt
print(f"### LOCAL stdio ({el}s)  isError={res.get('isError')}  payload_chars={len(pay)}")
print("    stderr:", " | ".join(l.strip() for l in errlines if l.strip())[:400])

# ---- HOSTED, with proper session ----
from mcp_client import rpc
t0=time.time()
r2 = rpc("tools/call", {"name":"scrape_as_markdown","arguments":{"url":URL}})
res2 = (r2 or {}).get("result", {}) or {}
c2 = res2.get("content", []); txt2 = c2[0].get("text","") if c2 else ""
pay2 = txt2.split("_BEGIN=====",1)[1].rsplit("=====UNTRUSTED",1)[0].strip() if "_BEGIN=====" in txt2 else txt2
print(f"### HOSTED ({round(time.time()-t0,1)}s)  isError={res2.get('isError')}  payload_chars={len(pay2)}")
print("    ", repr(pay2[:180]))
