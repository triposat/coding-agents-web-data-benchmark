"""Single source of truth for every figure the article may cite.
Anything not printed here does not go in the article."""
import json, collections, os

E = {}
ARMS = [("arm1_plain_http","Plain HTTP + browser UA"),
        ("arm2_local_browser","Local headless Chromium"),
        ("arm3_brightdata_mcp","Bright Data hosted Web MCP")]
data = {a: json.load(open(f"data/{a}.json")) for a,_ in ARMS}

skus = json.load(open("data/skus.json"))
E["targets"] = {"products": len(skus), "pages": sum(len(s["retailers"]) for s in skus),
                "retailers": sorted({r for s in skus for r in s["retailers"]}),
                "per_retailer": dict(collections.Counter(r for s in skus for r in s["retailers"]))}

E["arms"] = {}
for a, label in ARMS:
    rows = data[a]; c = collections.Counter(r["outcome"] for r in rows)
    lat = sorted(r["elapsed_s"] for r in rows)
    fields = {f: sum(1 for r in rows if r.get(f)) for f in ("name","price","availability","rating")}
    E["arms"][a] = {
        "label": label, "n": len(rows),
        "outcomes": dict(c),
        "success": c["success"], "success_pct": round(100*c["success"]/len(rows), 1),
        "blocked_total": sum(v for k,v in c.items() if k.startswith("blocked")),
        "latency_p50": lat[len(lat)//2], "latency_p90": lat[int(.9*len(lat))],
        "latency_max": max(lat), "latency_total": round(sum(lat)),
        "fields": fields, "field_total": sum(fields.values()), "field_max": 4*len(rows),
        "field_pct": round(100*sum(fields.values())/(4*len(rows))),
        "by_retailer": {ret: {"n": sum(1 for r in rows if r["retailer"]==ret),
                              "success": sum(1 for r in rows if r["retailer"]==ret and r["outcome"]=="success")}
                        for ret in E["targets"]["retailers"]},
    }

if os.path.exists("data/reliability_trials.json"):
    rel = json.load(open("data/reliability_trials.json"))
    E["reliability"] = {t: {"n": sum(1 for r in rel if r["target"]==t),
                            "silent_empty": sum(1 for r in rel if r["target"]==t and r.get("empty_no_error"))}
                        for t in {r["target"] for r in rel}}
    E["reliability"]["overall"] = {"n": len(rel), "silent_empty": sum(1 for r in rel if r.get("empty_no_error"))}

tools = json.load(open("data/mcp_tools.json"))
try:
    import tiktoken; enc = tiktoken.get_encoding("cl100k_base")
    E["mcp_tools"] = {"count": len(tools), "tools_list_tokens": len(enc.encode(json.dumps(tools))),
                      "encoder": "tiktoken cl100k_base", "names": [t["name"] for t in tools]}
except Exception:
    E["mcp_tools"] = {"count": len(tools), "names": [t["name"] for t in tools]}

for cond in ("claude_nobd","claude_bd"):
    p = f"runs/{cond}/result.json"
    if os.path.exists(p) and os.path.getsize(p):
        d = json.load(open(p)); u = d.get("usage", {})
        E.setdefault("agents", {})[cond] = {
            "turns": d.get("num_turns"), "duration_ms": d.get("duration_ms"),
            "cost_usd": d.get("total_cost_usd"), "is_error": d.get("is_error"),
            "input": u.get("input_tokens"), "output": u.get("output_tokens"),
            "cache_read": u.get("cache_read_input_tokens"),
            "cache_creation": u.get("cache_creation_input_tokens"),
            "models": list(d.get("modelUsage", {}).keys()),
        }
json.dump(E, open("data/EVIDENCE.json","w"), indent=2)
print(json.dumps(E, indent=2)[:3000])
