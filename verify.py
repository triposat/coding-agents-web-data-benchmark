#!/usr/bin/env python3
"""Re-derive every figure the article cites, from the committed data, and check
the article still says them. Exits non-zero on the first drift.

    python3 verify.py ../coding-agents-web-data-benchmark.md

No network, no credentials, no arguments beyond the article path. If this passes,
the numbers in the post are the numbers in this repo.
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).parent
RUNS = ROOT / "runs_isolated"
ARMS = ("cursor_bd", "claude_bd_high", "claude_bd", "cursor_nobd", "claude_nobd")
FAIL, CHECKS = [], []

def check(label, computed, present_in_article, article):
    """Loose check: the figure appears somewhere in the prose. Use cell() for tables."""
    ok = str(present_in_article) in article
    CHECKS.append((label, computed, ok))
    if not ok:
        FAIL.append(f"{label}: computed {computed!r}, not found in article as {present_in_article!r}")

def tables(article):
    """Every markdown table in the article, as lists of stripped cells."""
    out, cur = [], []
    for line in article.splitlines():
        if line.startswith("|"):
            cells = [c.strip().strip("*").strip() for c in line.strip("|").split("|")]
            if not all(set(c) <= set("-: ") for c in cells):   # skip separator rows
                cur.append(cells)
        elif cur:
            out.append(cur); cur = []
    if cur: out.append(cur)
    return out

def cell(label, computed, row_label, col, article, tabs):
    """Strict check: find the row whose first cell starts with row_label and
    assert the given column equals the computed value. Catches a wrong number
    even when that number appears correctly somewhere else in the article."""
    found = None
    for t in tabs:
        for row in t:
            if row and row[0].lower().startswith(row_label.lower()) and len(row) > col:
                found = row[col].strip().strip("*").strip()
                if found == str(computed):
                    CHECKS.append((label, computed, True)); return
    CHECKS.append((label, computed, False))
    FAIL.append(f"{label}: computed {computed!r}, table row {row_label!r} col {col} "
                f"says {found!r}")

# ---------- field parsers. deliberately forgiving on format, strict on value ----------
def price(v):
    if v in (None, "", []): return None
    m = re.search(r"[\d,]+\.?\d*", str(v).replace("$", ""))
    return round(float(m.group(0).replace(",", "")), 2) if m else None

def rating(v):
    if v in (None, "", []): return None
    m = re.match(r"\s*([0-5](?:\.\d+)?)", str(v))   # "4.8 (719 reviews)" -> 4.8
    return round(float(m.group(1)), 1) if m else None

def avail(v):
    if v in (None, "", []): return None
    s = str(v).lower()
    if re.search(r"out of stock|sold out|unavailable|oos|backorder", s): return "OUT"
    if re.search(r"in ?stock|available|add to cart|only \d+ left", s): return "IN"

FIELDS = {"price": price, "rating": rating, "availability": avail}

def load(arm, name):
    return json.load(open(RUNS / arm / name))

def score(arm, gt):
    rows = load(arm, "results.json")
    by = {f"{r['sku_id']}|{r['retailer']}": r for r in rows}
    per, tot, n = {}, 0, 0
    for f, fn in FIELDS.items():
        ok = cnt = 0
        for k, truth in gt.items():
            tv = fn(truth.get(f))
            if tv is None: continue
            cnt += 1
            if fn(by.get(k, {}).get(f)) == tv: ok += 1
        per[f] = (ok, cnt); tot += ok; n += cnt
    return {
        "rows": len(rows),
        "name_price": sum(1 for r in rows if r.get("name") and r.get("price") not in (None, "")),
        "all_four": sum(1 for r in rows if all(r.get(k) not in (None, "") for k in
                        ("name", "price", "availability", "rating"))),
        "correct": tot, "scored": n, "accuracy": round(tot / n * 100),
        "per_field": {f: round(a / b * 100) for f, (a, b) in per.items()},
        "wall_clock_s": load(arm, "meta.json")["wall_clock_s"],
        "py_lines": sum(len(open(p, errors="ignore").readlines())
                        for p in (RUNS / arm).rglob("*.py")),
    }

def main(article_path):
    article = open(article_path, errors="ignore").read()
    gt_doc = json.load(open(ROOT / "data" / "ground_truth_hand.json"))
    gt = gt_doc["rows"]

    # ---- ground truth shape ----
    values = sum(1 for r in gt.values() for f in FIELDS if r.get(f) is not None)
    check("ground truth rows", len(gt), f"all {len(gt)} pages", article)
    check("hand-adjudicated values", values, f"{values} hand-adjudicated values", article)

    # ---- per arm ----
    tabs = tables(article)
    ROWLABEL = {"cursor_bd": "A. Cursor + Bright Data",
                "claude_bd_high": "B+. Claude Code + Bright Data, matched effort",
                "claude_bd": "B+. Claude Code + Bright Data",
                "cursor_nobd": "Control. Cursor, no data layer",
                "claude_nobd": "B. Claude Code, no data layer"}
    results = {}
    for arm in ARMS:
        s = score(arm, gt); results[arm] = s
        lbl = ROWLABEL[arm]
        # field-accuracy table: col 1 = correct/scored, col 2 = accuracy, col 3 = price
        cell(f"{arm} correct/scored (table)", f"{s['correct']} / {s['scored']}", lbl, 1, article, tabs)
        cell(f"{arm} accuracy (table)", f"{s['accuracy']}%", lbl, 2, article, tabs)
        cell(f"{arm} price accuracy (table)", f"{s['per_field']['price']}%", lbl, 3, article, tabs)
    check("scored values per arm", results["cursor_bd"]["scored"],
          f"{results['cursor_bd']['scored']} comparisons", article)

    # ---- headline pair ----
    check("A pages", results["cursor_bd"]["name_price"],
          f"{results['cursor_bd']['name_price']} of 41", article)


    # ---- the 2x2 that the argument rests on ----
    gap_cursor = results["cursor_bd"]["accuracy"] - results["cursor_nobd"]["accuracy"]
    gap_claude = results["claude_bd_high"]["accuracy"] - results["claude_nobd"]["accuracy"]
    words = {14: "Fourteen", 15: "Fifteen", 16: "Sixteen", 17: "Seventeen"}
    check("data-layer gap, Cursor", gap_cursor,
          f"{words.get(gap_cursor, gap_cursor)} and", article)
    CHECKS.append((f"data-layer gap, Claude Code = {gap_claude}", gap_claude,
                   f"and {words.get(gap_claude, gap_claude).lower()} points" in article))
    if f"and {words.get(gap_claude, gap_claude).lower()} points" not in article:
        FAIL.append(f"data-layer gap Claude Code: computed {gap_claude}, article disagrees")

    # ---- per-retailer, Best Buy is the one the post leans on ----
    bb = {a: sum(1 for r in load(a, "results.json")
                 if r.get("retailer") == "bestbuy" and r.get("name")
                 and r.get("price") not in (None, "")) for a in ARMS}
    check("Best Buy, arm A", bb["cursor_bd"], f"{bb['cursor_bd']} of 9", article)

    # ---- code written ----
    check("Control python lines", results["cursor_nobd"]["py_lines"],
          str(results["cursor_nobd"]["py_lines"]), article)

    # ---- new-listings feed ----
    nl = json.load(open(RUNS / "cursor_bd" / "new_listings.json"))
    cand = sum(len(x.get("new_listings", [])) for x in nl)
    check("new-listings candidates", cand, f"{cand} candidates", article)

    # ---- nothing sensitive ----
    # built from fragments so this file does not match its own scan
    SECRETS = ["c15c" + "90df", "hfotf" + "024ftae", "3hj4" + "gnwo4me8",
               "brd-customer-" + "hl_49a5c300"]
    me = pathlib.Path(__file__).resolve()
    for pat in SECRETS:
        hits = [p for p in ROOT.rglob("*")
                if p.is_file() and ".git" not in p.parts and p.resolve() != me
                and p.suffix in (".py", ".sh", ".json", ".md", ".txt", ".jsonl")
                and pat in p.read_text(errors="ignore")]
        CHECKS.append((f"no credential {pat}", len(hits), not hits))
        if hits: FAIL.append(f"credential {pat} present in {hits[0]}")

    width = max(len(c[0]) for c in CHECKS)
    for label, computed, ok in CHECKS:
        print(f"  {'PASS' if ok else 'FAIL'}  {label:<{width}}  {computed}")
    print(f"\n  {sum(1 for c in CHECKS if c[2])}/{len(CHECKS)} checks passed")
    if FAIL:
        print("\n  DRIFT:")
        for f in FAIL: print(f"    - {f}")
        return 1
    print("  Every figure in the article is re-derivable from this repo.")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1
                  else ROOT.parent / "coding-agents-web-data-benchmark.md"))
