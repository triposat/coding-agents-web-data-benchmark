"""Accuracy of the Web Scraper API's typed records against the hand ground truth.
Field names differ per retailer and some are nested, so the mapping is explicit
rather than guessed: an earlier pass read Walmart's star histogram as a rating."""
import json, re, glob
GT = json.load(open('data/ground_truth_hand.json'))['rows']
url2key = {}
for r in json.load(open('data/skus.json')):
    for ret, i in r['retailers'].items():
        url2key[i['url'].split('?')[0].rstrip('/')] = f"{r['sku_id']}|{ret}"
# per-retailer field mapping, read off the records themselves
MAP = {
  "amazon":  {"price": ["final_price", "initial_price"], "rating": ["rating"],     "avail": ["availability", "is_available"]},
  "walmart": {"price": ["final_price", "price"],         "rating": ["rating"],     "avail": ["availability_text", "available_for_delivery"]},
  "newegg":  {"price": ["sale_price", "price"],          "rating": ["star_rating"],"avail": ["availability"]},
  "target":  {"price": ["price.value"],                  "rating": ["rating.average", "average_rating"], "avail": ["availability", "in_stock"]},
}
def dig(row, path):
    cur = row
    for part in path.split("."):
        if not isinstance(cur, dict): return None
        cur = cur.get(part)
    return cur if not isinstance(cur, (dict, list)) else None
def first(row, paths):
    for p in paths:
        v = dig(row, p)
        if v not in (None, "", []): return v
def num(v, lo=None, hi=None):
    if v in (None, "", []): return None
    m = re.search(r"[\d,]+\.?\d*", str(v).replace("$", ""))
    if not m: return None
    f = float(m.group(0).replace(",", ""))
    if lo is not None and not (lo <= f <= hi): return None
    return round(f, 2)
def avail(v):
    if v in (None, "", []): return None
    if isinstance(v, bool): return "IN" if v else "OUT"
    s = str(v).lower()
    if re.search(r"out.of.stock|sold.out|unavailable|^false$", s): return "OUT"
    if re.search(r"in.?stock|available|^true$", s): return "IN"
recs = {}
for f in glob.glob('data/structured_*.json'):
    if any(t in f for t in ('all', 'snapshot', 'summary')): continue
    d = json.load(open(f)); rows = d if isinstance(d, list) else d.get('rows', [])
    for row in rows:
        k = url2key.get(str(row.get('url', '')).split('?')[0].rstrip('/'))
        if k: recs[k] = row
per = {"price": [0, 0], "rating": [0, 0], "availability": [0, 0]}
for k, t in GT.items():
    row = recs.get(k)
    if not row: continue
    m = MAP.get(k.split("|")[1])
    if not m: continue
    for fld, key, fn in (("price", "price", lambda v: num(v)),
                         ("rating", "rating", lambda v: (lambda x: round(x,1) if x is not None else None)(num(v,0,5))),
                         ("availability", "avail", avail)):
        tv = {"price": lambda v: num(v), "rating": lambda v: (lambda x: round(x,1) if x is not None else None)(num(v,0,5)),
              "availability": avail}[fld](t.get(fld))
        if tv is None: continue
        per[fld][1] += 1
        if fn(first(row, m[key])) == tv: per[fld][0] += 1
tot = sum(v[0] for v in per.values()); n = sum(v[1] for v in per.values())
print(f"  structured records matched: {len(recs)} of 41 pages")
for f, (a, b) in per.items():
    if b: print(f"    {f:13} {a}/{b} = {a/b*100:.0f}%")
print(f"    {'ALL':13} {tot}/{n} = {tot/n*100:.0f}%")
