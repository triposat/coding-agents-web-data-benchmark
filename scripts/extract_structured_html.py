"""Pull price out of the machine-readable structures retail pages already embed,
instead of picking a currency token out of prose. Markdown conversion discards
all of this. Scored against the same hand ground truth as every other arm."""
import gzip, glob, json, re, sys
def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values(): yield from walk(v)
    elif isinstance(o, list):
        for v in o: yield from walk(v)
PRICE_KEYS = ("price", "currentprice", "current_price", "saleprice", "sale_price",
              "listprice", "list_price", "finalprice", "final_price", "offerprice")
def plausible(v):
    try: f = float(str(v).replace("$", "").replace(",", "").strip())
    except Exception: return None
    return round(f, 2) if 1.0 <= f <= 100000 else None
def from_jsonld(html):
    out = []
    for b in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try: d = json.loads(b)
        except Exception: continue
        for node in walk(d):
            for k, v in node.items():
                if k.lower() in PRICE_KEYS:
                    p = plausible(v.get("value") if isinstance(v, dict) else v)
                    if p: out.append(p)
    return out
def from_nextdata(html):
    m = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m: return []
    try: d = json.loads(m.group(1))
    except Exception: return []
    out = []
    for node in walk(d):
        for k, v in node.items():
            if k.lower() in PRICE_KEYS:
                p = plausible(v.get("value") if isinstance(v, dict) else v)
                if p: out.append(p)
    return out
def from_itemprop(html):
    return [p for p in (plausible(v) for v in
            re.findall(r'itemprop=["\']price["\'][^>]*content=["\']([^"\']+)', html, re.I)) if p]
def price_of(html):
    """Most frequent plausible price across all embedded structures wins; a page
    repeats its real price and mentions accessories once."""
    cands = from_jsonld(html) + from_nextdata(html) + from_itemprop(html)
    if not cands: return None, 0
    counts = {}
    for c in cands: counts[c] = counts.get(c, 0) + 1
    best = max(counts.items(), key=lambda kv: (kv[1], -kv[0]))
    return best[0], len(cands)
if __name__ == "__main__":
    GT = json.load(open("data/ground_truth_hand.json"))["rows"]
    ok = wrong = missing = 0; rowlog = []
    for f in sorted(glob.glob("data/payloads/gt__*.html.gz")):
        sku = f.split("__")[1]; ret = f.split("__")[2].replace(".html.gz", "")
        key = f"{sku}|{ret}"
        truth = GT.get(key, {}).get("price")
        if truth in (None, ""): continue
        tv = round(float(truth), 2)
        html = gzip.open(f, "rt", errors="ignore").read()
        got, n = price_of(html)
        if got is None: missing += 1; verdict = "no structured price"
        elif got == tv: ok += 1; verdict = "match"
        else: wrong += 1; verdict = f"got {got}"
        rowlog.append((key, tv, got, verdict))
    tot = ok + wrong + missing
    print(f"  structured extraction from HTML, price only, {tot} scoreable pages")
    print(f"    match   {ok}/{tot} = {ok/tot*100:.0f}%")
    print(f"    wrong   {wrong}")
    print(f"    absent  {missing}")
    print(f"\n  arm A, agent reading markdown, price: 80%")
    print("\n  mismatches:")
    for k, tv, got, v in rowlog:
        if v != "match": print(f"    {k:14} truth={tv:<9} {v}")
