"""Re-derive the fetch arms from the COMMITTED payloads with a corrected extractor.

Two bugs in the original:
  1. title_of() returned markdown line 1, which on Amazon is a ``` fence.
  2. price took the FIRST currency token, which on a retail page is routinely a
     protection plan, an accessory, or a financing figure.

Fix for (2): the real selling price is repeated across the page (buybox, sticky
header, cart module) while decoys appear once or twice. Take the most frequent
currency token, tie-broken by the larger value.
"""
import json, re, sys, collections, pathlib

PRICE_TOK = re.compile(r"\$\s?([0-9][0-9,]{0,6}\.[0-9]{2})")
RATING_RX = [re.compile(r'"ratingValue"\s*:\s*"?([0-5](?:\.[0-9])?)'),
             re.compile(r'([0-5]\.[0-9])\s*out of\s*5')]
AVAIL = [(re.compile(r"\bcurrently unavailable\b", re.I), "OutOfStock"),
         (re.compile(r"\bout of stock\b", re.I), "OutOfStock"),
         (re.compile(r"\bsold out\b", re.I), "OutOfStock"),
         (re.compile(r"\bin stock\b", re.I), "InStock"),
         (re.compile(r"\badd to cart\b", re.I), "InStock"),
         (re.compile(r"\badd to bag\b", re.I), "InStock")]

def title_of(text):
    for line in text.split("\n")[:40]:
        s = line.strip()
        if not s or s.startswith("```") or set(s) <= set("`#-|= "):
            continue
        s = re.sub(r"^#+\s*", "", s).strip()
        if len(s) >= 15:
            return s[:200]
    return None

def price_of(text):
    toks = [t.replace(",", "") for t in PRICE_TOK.findall(text)]
    if not toks:
        return None
    c = collections.Counter(toks)
    top = max(c.items(), key=lambda kv: (kv[1], float(kv[0])))
    return top[0]

def rating_of(text):
    for rx in RATING_RX:
        m = rx.search(text)
        if m:
            return m.group(1)
    return None

def avail_of(text):
    for rx, v in AVAIL:
        if rx.search(text):
            return v
    return None

ARMS = {"arm1_plain_http": ("arm1_plain_http", "txt"), "arm2_local_browser": ("arm2_local_browser", "txt"), "arm3_brightdata_mcp": ("arm3", "md")}
out = {}
for arm, (prefix, ext) in ARMS.items():
    rows = json.load(open(f"data/{arm}.json"))
    fixed = []
    for r in rows:
        p = pathlib.Path(f"data/payloads/{prefix}__{r["sku_id"]}__{r["retailer"]}.{ext}")
        body = p.read_text(errors="ignore") if p.exists() else ""
        n = dict(r)
        if body.strip():
            n["name"] = title_of(body); n["price"] = price_of(body)
            n["rating"] = rating_of(body); n["availability"] = avail_of(body)
        else:
            n["name"] = n["price"] = n["rating"] = n["availability"] = None
        fixed.append(n)
    json.dump(fixed, open(f"data/{arm}_reextracted.json", "w"), indent=2)
    npx = sum(1 for x in fixed if x["name"] and x["price"])
    a4 = sum(1 for x in fixed if all(x[f] for f in ("name","price","availability","rating")))
    fc = {f: sum(1 for x in fixed if x[f]) for f in ("name","price","availability","rating")}
    byr = collections.Counter(x["retailer"] for x in fixed if x["name"] and x["price"])
    out[arm] = dict(name_price=npx, all_four=a4, fields=fc, field_total=sum(fc.values()), by_retailer=dict(byr))
    print(f"{arm:24} name+price={npx:3}  all4={a4:3}  fields={sum(fc.values()):3}/164  {dict(byr)}")
json.dump(out, open("data/reextract_summary.json","w"), indent=2)
