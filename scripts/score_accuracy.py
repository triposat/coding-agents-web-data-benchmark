"""Field accuracy for every run against the hand-verified ground truth.

Scored only on the 25 hand-adjudicated rows. A value is correct when it matches
the human-read value. Reporting null where the page shows no value is CORRECT;
inventing a value there is wrong, which is the behaviour this metric exists to catch.
"""
import json, pathlib

GT = json.load(open("data/ground_truth_hand.json"))["rows"]
RUNS = {"cursor_bd": "A  Cursor + Bright Data", "cursor_nobd": "Control  Cursor, no BD",
        "claude_bd": "B+ Claude Code + BD", "claude_nobd_v2": "B  Claude Code, no BD"}
FIELDS = ("price", "rating", "availability")

def norm(v, f):
    if v in (None, "", "null"):
        return None
    s = str(v).strip()
    if f in ("price", "rating"):
        try: return f"{float(s.replace(',','').replace('$','')):.2f}"
        except ValueError: return s.lower()
    s = s.lower()
    if "out of stock" in s or "unavailable" in s or "sold out" in s: return "outofstock"
    if "in stock" in s or "instock" in s or "available" in s: return "instock"
    return s

print(f"{'run':26} {'scored':>7} {'correct':>8} {'accuracy':>9} {'wrong-value':>12} {'invented':>9} {'missed':>7}")
print("-" * 84)
out = {}
for run, label in RUNS.items():
    p = pathlib.Path(f"runs/{run}/results.json")
    if not p.exists(): continue
    rows = {f"{x['sku_id']}|{x['retailer']}": x for x in json.load(open(p))}
    scored = correct = wrong = invented = missed = 0
    for key, truth in GT.items():
        got = rows.get(key)
        if got is None: continue
        for f in FIELDS:
            t, g = norm(truth[f], f), norm(got.get(f), f)
            scored += 1
            if t == g: correct += 1
            elif t is None and g is not None: invented += 1
            elif t is not None and g is None: missed += 1
            else: wrong += 1
    acc = round(100 * correct / scored) if scored else 0
    out[run] = dict(scored=scored, correct=correct, accuracy_pct=acc,
                    wrong_value=wrong, invented=invented, missed=missed)
    print(f"{label:26} {scored:>7} {correct:>8} {str(acc)+'%':>9} {wrong:>12} {invented:>9} {missed:>7}")
json.dump(out, open("data/field_accuracy.json", "w"), indent=2)
