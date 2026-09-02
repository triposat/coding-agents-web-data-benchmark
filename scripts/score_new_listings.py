"""Score the SERP-driven new-listings feed, which the brief asks for and which
every run produced but nobody checked.

A candidate counts only if it is a real URL, on a retailer not already in
skus.json, and not a duplicate. We then fetch a sample to see how many resolve.
"""
import json, re, pathlib, collections
from urllib.parse import urlparse

skus = json.load(open("data/skus.json"))
known = {urlparse(d["url"]).netloc.replace("www.", "") for s in skus for d in s["retailers"].values()}
KEYS = ("new_listings", "new_retailer_urls", "listings", "urls")

def extract(run):
    p = pathlib.Path(f"runs/{run}/new_listings.json")
    if not p.exists(): return None
    d = json.load(open(p))
    rows = d if isinstance(d, list) else list(d.values())
    out = []
    for r in rows:
        if not isinstance(r, dict): continue
        cands = next((r[k] for k in KEYS if k in r and r[k]), [])
        for c in cands:
            u = c if isinstance(c, str) else (c.get("url") or "")
            if u: out.append((r.get("sku_id"), u))
    return out

print(f"{'run':18} {'candidates':>11} {'valid url':>10} {'new domain':>11} {'unique':>8} {'domains':>8}")
summary = {}
for run in ("cursor_bd", "cursor_nobd", "claude_bd", "claude_nobd_v2"):
    got = extract(run)
    if got is None:
        print(f"{run:18} {'no file':>11}"); continue
    valid = [(s, u) for s, u in got if re.match(r"^https?://[^\s]+\.[a-z]{2,}", u or "")]
    fresh = [(s, u) for s, u in valid if urlparse(u).netloc.replace("www.", "") not in known]
    uniq = {u for _, u in fresh}
    doms = {urlparse(u).netloc.replace("www.", "") for u in uniq}
    summary[run] = dict(candidates=len(got), valid=len(valid), new_domain=len(fresh),
                        unique=len(uniq), domains=len(doms),
                        top_domains=[d for d, _ in collections.Counter(
                            urlparse(u).netloc.replace("www.", "") for u in uniq).most_common(5)])
    print(f"{run:18} {len(got):>11} {len(valid):>10} {len(fresh):>11} {len(uniq):>8} {len(doms):>8}")
json.dump(summary, open("data/new_listings_summary.json", "w"), indent=2)
print()
for r, v in summary.items(): print(f"  {r:18} top domains: {', '.join(v['top_domains'])}")
