"""Arm 3: the same 41 URLs through Bright Data MCP scrape_as_markdown.
Records payload length so the silent-empty case is visible, not hidden."""
import sys, json, time; sys.path.insert(0, "scripts")
from mcp_client import rpc
from extract import classify

skus = json.load(open("data/skus.json"))
TARGETS = [(s["sku_id"], s["product"], r, d["url"])
           for s in skus for r, d in s["retailers"].items()]
rows = []
for sid, prod, ret, url in TARGETS:
    t0 = time.time()
    body, err = "", None
    try:
        r = rpc("tools/call", {"name": "scrape_as_markdown", "arguments": {"url": url}})
        res = (r or {}).get("result", {}); c = res.get("content", [])
        text = c[0].get("text", "") if c else ""
        body = text.split("_BEGIN=====", 1)[1].rsplit("=====UNTRUSTED", 1)[0].strip() if "_BEGIN=====" in text else ""
        if (r or {}).get("error"):
            err = json.dumps(r["error"])[:150]
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:120]}"
    outcome, fields = classify(200 if body else None, body, err, is_markdown=True)
    if not body and not err:
        outcome = "blocked_empty"      # 200-shaped success, zero payload
    row = {"arm": "arm3_brightdata_mcp", "sku_id": sid, "product": prod, "retailer": ret,
           "url": url, "elapsed_s": round(time.time()-t0, 2), "bytes": len(body),
           "outcome": outcome, "error": err, **fields}
    open(f"data/payloads/arm3__{sid}__{ret}.md","w").write(body or "")
    rows.append(row)
    print(json.dumps({k: row[k] for k in ("sku_id","retailer","outcome","elapsed_s","bytes")}), flush=True)
json.dump(rows, open("data/arm3_brightdata_mcp.json", "w"), indent=2)
from collections import Counter
print("\n=== arm3 ===", Counter(r["outcome"] for r in rows), file=sys.stderr)
