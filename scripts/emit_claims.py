#!/usr/bin/env python3
"""Emit every published figure as a machine-readable claim with its provenance.

    python3 scripts/emit_claims.py > claims.json

Each claim carries the value, where it was derived from, and what computed it, so
an agent can check the post without parsing prose. Values come from the same
functions verify.py uses, so the two cannot disagree.
"""
import json, pathlib, re, subprocess, sys, datetime
ROOT = pathlib.Path(__file__).parent.parent
RUNS = ROOT / "runs_isolated"
ARMS = {"cursor_bd": "A. Cursor CLI + Bright Data",
        "claude_bd_high": "B+. Claude Code + Bright Data, matched effort",
        "claude_bd": "B+. Claude Code + Bright Data",
        "cursor_nobd": "Control. Cursor CLI, no data layer",
        "claude_nobd": "B. Claude Code, no data layer"}
def price(v):
    if v in (None, ""): return None
    m = re.search(r"[\d,]+\.?\d*", str(v).replace("$", ""))
    return round(float(m.group(0).replace(",", "")), 2) if m else None
def rating(v):
    if v in (None, ""): return None
    m = re.match(r"\s*([0-5](?:\.\d+)?)", str(v))
    return round(float(m.group(1)), 1) if m else None
def avail(v):
    if v in (None, ""): return None
    s = str(v).lower()
    if re.search(r"out of stock|sold out|unavailable|oos|backorder", s): return "OUT"
    if re.search(r"in ?stock|available|add to cart|only \d+ left", s): return "IN"
FIELDS = {"price": price, "rating": rating, "availability": avail}
gt = json.load(open(ROOT / "data" / "ground_truth_hand.json"))["rows"]
claims, scores = [], {}
def add(cid, value, unit, derived, computed, note=""):
    claims.append({"id": cid, "value": value, "unit": unit,
                   "derived_from": derived, "computed_by": computed, "note": note})
for arm, label in ARMS.items():
    rows = json.load(open(RUNS / arm / "results.json"))
    by = {f"{r['sku_id']}|{r['retailer']}": r for r in rows}
    ok = n = 0; per = {}
    for f, fn in FIELDS.items():
        a = b = 0
        for k, t in gt.items():
            tv = fn(t.get(f))
            if tv is None: continue
            b += 1
            if fn(by.get(k, {}).get(f)) == tv: a += 1
        per[f] = round(a / b * 100); ok += a; n += b
    scores[arm] = round(ok / n * 100)
    src = f"runs_isolated/{arm}/results.json"
    add(f"{arm}.field_accuracy", round(ok / n * 100), "percent", src, "scripts/score_accuracy_iso.py", label)
    add(f"{arm}.values_correct", ok, "count", src, "scripts/score_accuracy_iso.py", f"of {n} scored")
    add(f"{arm}.pages_name_and_price",
        sum(1 for r in rows if r.get("name") and r.get("price") not in (None, "")),
        "count", src, "verify.py", "of 41 pages")
    for f, v in per.items():
        add(f"{arm}.{f}_accuracy", v, "percent", src, "scripts/score_accuracy_iso.py", label)
    add(f"{arm}.wall_clock_s", json.load(open(RUNS / arm / "meta.json"))["wall_clock_s"],
        "seconds", f"runs_isolated/{arm}/meta.json", "harness")
add("ground_truth.rows", len(gt), "count", "data/ground_truth_hand.json", "hand adjudication")
add("ground_truth.values", sum(1 for r in gt.values() for f in FIELDS if r.get(f) is not None),
    "count", "data/ground_truth_hand.json", "hand adjudication")
add("data_layer_gap.cursor", scores["cursor_bd"] - scores["cursor_nobd"], "percentage_points",
    "runs_isolated/", "scripts/score_accuracy_iso.py", "same agent, data layer removed")
add("data_layer_gap.claude_code", scores["claude_bd_high"] - scores["claude_nobd"], "percentage_points",
    "runs_isolated/", "scripts/score_accuracy_iso.py", "same agent and effort, data layer removed")
try:
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip() or None
except Exception: commit = None
json.dump({
    "$comment": "Every figure published in the accompanying article, with provenance. "
                "Run `python3 verify.py <article.md>` to check the article still matches.",
    "generated": datetime.date.today().isoformat(),
    "commit": commit,
    "task": {"pages": 41, "retailers": 5, "products": 10,
             "model": "claude-sonnet-5", "sku_list": "data/skus.json"},
    "claims": claims,
}, sys.stdout, indent=2)
print()
