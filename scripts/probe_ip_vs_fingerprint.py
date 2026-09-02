"""13 of 15 sites refused all three local clients identically, which rules out the
transport fingerprint as the discriminator. The remaining candidate is the IP.
Same URLs, same minute, through Bright Data's egress instead of this machine's."""
import json, os, re, time, urllib.request
K = os.environ["BD_KEY"]
CHALLENGE = re.compile(r"captcha|are you a human|robot or human|verify you are|access denied|"
                       r"unusual traffic|enable javascript to continue|press & hold|blocked", re.I)
def classify(body):
    if not body: return "empty"
    if CHALLENGE.search(body[:200000]): return "challenge_page"
    return "ok" if len(body) > 20000 else "thin_body"
rows = json.load(open("data/refusal_layer.json"))
out = []
for r in rows:
    body = ""
    t0 = time.time()
    try:
        rq = urllib.request.Request("https://api.brightdata.com/request",
            data=json.dumps({"zone": "web_unlocker", "url": r["url"], "format": "json"}).encode(),
            headers={"Authorization": f"Bearer {K}", "Content-Type": "application/json"})
        d = json.loads(urllib.request.urlopen(rq, timeout=180).read())
        status = d.get("status_code"); body = d.get("body", "") or ""
        res = f"http_{status}" if status and status >= 400 else classify(body)
    except Exception as e:
        res = f"error"
    out.append({**r, "brightdata": res, "bd_secs": round(time.time()-t0, 1), "bd_bytes": len(body)})
    print(f"  {r['site']:13} local(all 3)={r['urllib']:16} brightdata={res:16} {len(body):>8,}b", flush=True)
json.dump(out, open("data/refusal_layer.json", "w"), indent=2)
ok_bd = sum(1 for x in out if x["brightdata"] == "ok")
ok_local = sum(1 for x in out if x["chromium"] == "ok")
print(f"\n  reachable from this machine, best local client: {ok_local}/{len(out)}")
print(f"  reachable through Bright Data's egress:         {ok_bd}/{len(out)}")
