"""Field accuracy for the isolated arms against the 41-row hand ground truth.
Parsers are deliberately forgiving about format and strict about value: a rating
written "4.8 (719 reviews)" is the same answer as "4.8", but 4.6 is not 4.8."""
import json, pathlib, re, sys
GT = json.load(open('data/ground_truth_hand.json'))['rows']
BASE = pathlib.Path(sys.argv[1])
RUNS = ("cursor_bd", "claude_nobd", "claude_bd", "cursor_nobd")
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
    return None
FN = {"price": price, "rating": rating, "availability": avail}
print(f"{'run':13} {'field':13} {'right':>6} {'wrong':>6} {'missing':>8} {'accuracy':>9}")
summary = {}
for c in RUNS:
    rows = {f"{r['sku_id']}|{r['retailer']}": r for r in json.load(open(BASE/c/"results.json"))}
    tot_ok = tot_n = 0
    for f, fn in FN.items():
        ok = wr = ms = 0
        for k, t in GT.items():
            tv = fn(t.get(f))
            if tv is None: continue
            gv = fn(rows.get(k, {}).get(f))
            if gv is None: ms += 1
            elif gv == tv: ok += 1
            else: wr += 1
        n = ok + wr + ms; tot_ok += ok; tot_n += n
        print(f"{c:13} {f:13} {ok:>6} {wr:>6} {ms:>8} {ok/n*100:>8.0f}%")
    summary[c] = (tot_ok, tot_n)
    print(f"{c:13} {'ALL':13} {tot_ok:>6} {'':>6} {'':>8} {tot_ok/tot_n*100:>8.0f}%  of {tot_n}\n")
json.dump({k: {"correct": v[0], "scored": v[1], "pct": round(v[0]/v[1]*100)} for k, v in summary.items()},
          open("data/accuracy_isolated.json", "w"), indent=2)
