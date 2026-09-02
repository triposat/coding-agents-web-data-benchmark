import json, re, glob, collections

RX = {
 "amazon":  re.compile(r"amazon\.com/(?:[^/\s\"]+/)?(?:dp|clp|gp/product)/([A-Z0-9]{10})"),
 "walmart": re.compile(r"walmart\.com/ip/(?:[^/\s\"?]+/)?(\d{6,})"),
 "bestbuy": re.compile(r"(bestbuy\.com/product/[^\s\"?]+/sku/\d{6,})"),
 "target":  re.compile(r"target\.com/p/[^\s\"?]*?/-/A-(\d{6,})"),
 "newegg":  re.compile(r"(newegg\.com/[^\s\"?]*?/p/[A-Z0-9]{8,})"),
}
CANON = {
 "amazon":  lambda m: f"https://www.amazon.com/dp/{m}",
 "walmart": lambda m: f"https://www.walmart.com/ip/{m}",
 "bestbuy": lambda m: f"https://www.{m}",
 "target":  lambda m: f"https://www.target.com/p/-/A-{m}",
 "newegg":  lambda m: f"https://www.{m}",
}
out = collections.defaultdict(dict)
for f in glob.glob("data/serp_*.json"):
    retailer = f.split("serp_")[1].rsplit("_", 1)[0]
    rx, canon = RX[retailer], CANON[retailer]
    for entry in json.load(open(f)):
        product = entry["query"].split(" ", 1)[1]
        hit = None
        for o in (entry.get("result", {}) or {}).get("organic", []) or []:
            m = rx.search(o.get("link", "") or "")
            if m:
                hit = {"url": canon(m.group(1)), "serp_title": o.get("title", "")[:110]}
                break
        if hit:
            out[product][retailer] = hit

skus = []
for i, (product, byret) in enumerate(sorted(out.items()), 1):
    skus.append({"sku_id": f"S{i:02d}", "product": product, "retailers": byret})
json.dump(skus, open("data/skus.json", "w"), indent=2)

print(f"{'PRODUCT':46} " + " ".join(f"{r:8}" for r in ["amazon","walmart","bestbuy","target","newegg"]))
tot = 0
for s in skus:
    marks = []
    for r in ["amazon","walmart","bestbuy","target","newegg"]:
        ok = r in s["retailers"]; tot += ok
        marks.append(f"{'YES' if ok else '-':8}")
    print(f"{s['product'][:45]:46} " + " ".join(marks))
print(f"\nTOTAL RESOLVED PRODUCT PAGES: {tot} across {len(skus)} products x 5 retailers")
