"""Print the authoritative context for each field so a human can adjudicate the
true value by reading the page, not by trusting a regex.

Stratified sample: 5 pages per retailer = 25 rows x 4 fields = 100 values, which
is the ~100-record hand-verified ground truth the brief asks for.
"""
import json, re, sys, pathlib

FL = ("name", "price", "availability", "rating")

def payload(sku, ret):
    for pre, ext in (("arm3", "md"), ("gt", "html")):
        p = pathlib.Path(f"data/payloads/{pre}__{sku}__{ret}.{ext}")
        if p.exists() and p.stat().st_size > 500:
            return p.read_text(errors="ignore"), p.name
    return "", None

def ctx(text, pat, n=3, w=95):
    out = []
    for m in re.finditer(pat, text, re.I):
        s = max(0, m.start() - w)
        out.append(re.sub(r"\s+", " ", text[s:m.end() + 40]).strip()[-(w + 45):])
        if len(out) >= n:
            break
    return out

skus = json.load(open("data/skus.json"))
rows = [(s["sku_id"], s["product"], r) for s in skus for r in s["retailers"]]
by_ret = {}
for sid, prod, ret in rows:
    by_ret.setdefault(ret, []).append((sid, prod))
sample = [(sid, prod, ret) for ret, lst in sorted(by_ret.items()) for sid, prod in lst[:5]]

only = sys.argv[1] if len(sys.argv) > 1 else None
for sid, prod, ret in sample:
    if only and ret != only:
        continue
    text, src = payload(sid, ret)
    print(f"\n{'='*100}\n{sid} / {ret}  ({prod})   src={src}  chars={len(text)}")
    if not text:
        print("  NO PAYLOAD"); continue
    print("  TITLE  :", (next((l.strip() for l in text.split('\n')[:40]
                              if len(l.strip()) >= 15 and not l.strip().startswith('```')), ""))[:110])
    for label, pat in (("PRICE  ", r"\$\s?[0-9][0-9,]{0,6}\.[0-9]{2}"),
                       ("RATING ", r"[0-5]\.[0-9]\s*out of\s*5|\"ratingValue\"\s*:\s*\"?[0-5]\.?[0-9]?"),
                       ("AVAIL  ", r"in stock|out of stock|add to cart|currently unavailable|sold out|add to bag")):
        for c in ctx(text, pat):
            print(f"  {label}:", c)
