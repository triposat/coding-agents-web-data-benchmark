"""What the RETURNED CONTENT costs the agent to read.

Tool definitions are the cost everyone quotes. The payload is the cost nobody
measures, and on retail pages it is three orders of magnitude larger.
"""
import pathlib, json
try:
    import tiktoken; enc = tiktoken.get_encoding("cl100k_base"); tok = lambda s: len(enc.encode(s))
    mode = "tiktoken cl100k_base"
except Exception:
    tok = lambda s: len(s)//4; mode = "approx len/4"

pages = [(p.name, tok(p.read_text(errors="ignore"))) for p in sorted(pathlib.Path("data/payloads").glob("arm3__*.md"))]
tot = sum(n for _, n in pages)
by_ret = {}
for name, n in pages:
    r = name.split("__")[2].replace(".md", "")
    by_ret.setdefault(r, []).append(n)

answer = tok(json.dumps(json.load(open("runs/claude_bd/results.json"))))
tools = tok(json.dumps(json.load(open("data/mcp_tools.json"))))

res = {
    "encoder": mode,
    "pages": len(pages),
    "markdown_tokens_total": tot,
    "markdown_tokens_median": sorted(n for _, n in pages)[len(pages)//2],
    "markdown_tokens_max": max(n for _, n in pages),
    "heaviest_page": max(pages, key=lambda x: x[1])[0],
    "structured_answer_tokens": answer,
    "tool_definition_tokens": tools,
    "waste_pct": round(100 * (1 - answer / tot), 1),
    "payload_vs_tooldefs": round(tot / tools),
    "by_retailer_median": {r: sorted(v)[len(v)//2] for r, v in sorted(by_ret.items())},
}
json.dump(res, open("data/token_cost.json", "w"), indent=2)
for k, v in res.items(): print(f"{k:26} {v}")
