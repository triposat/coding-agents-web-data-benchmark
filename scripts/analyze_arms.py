import json, collections, statistics
ARMS = [("arm1_plain_http","Plain HTTP + browser UA"),
        ("arm2_local_browser","Local headless Chromium"),
        ("arm3_brightdata_mcp","Bright Data Web MCP")]
data = {a: json.load(open(f"data/{a}.json")) for a,_ in ARMS}
RET = ["amazon","walmart","bestbuy","target","newegg"]

print("=" * 78)
print("OUTCOME DISTRIBUTION (n=41 product pages per arm)")
print("=" * 78)
print(f"{'arm':30} {'success':>8} {'no price':>9} {'blocked':>8} {'other':>7} {'succ %':>7}")
for a, label in ARMS:
    c = collections.Counter(r["outcome"] for r in data[a])
    s = c["success"]; np_ = c["partial_no_price"]
    blocked = sum(v for k,v in c.items() if k.startswith("blocked"))
    other = len(data[a]) - s - np_ - blocked
    print(f"{label:30} {s:>8} {np_:>9} {blocked:>8} {other:>7} {100*s/len(data[a]):>6.1f}%")

print()
print("=" * 78); print("SUCCESS BY RETAILER (all four fields readable)"); print("=" * 78)
print(f"{'retailer':10} {'n':>3} " + " ".join(f"{l.split()[0][:11]:>12}" for _,l in ARMS))
for ret in RET:
    n = sum(1 for r in data["arm1_plain_http"] if r["retailer"] == ret)
    cells = []
    for a,_ in ARMS:
        s = sum(1 for r in data[a] if r["retailer"]==ret and r["outcome"]=="success")
        cells.append(f"{s}/{n}".rjust(12))
    print(f"{ret:10} {n:>3} " + " ".join(cells))

print()
print("=" * 78); print("LATENCY, seconds per page"); print("=" * 78)
print(f"{'arm':30} {'p50':>7} {'p90':>7} {'max':>7} {'total':>9}")
for a, label in ARMS:
    lat = sorted(r["elapsed_s"] for r in data[a])
    p = lambda q: lat[min(len(lat)-1, int(q*len(lat)))]
    print(f"{label:30} {p(.5):>7.1f} {p(.9):>7.1f} {max(lat):>7.1f} {sum(lat):>8.0f}s")

print()
print("=" * 78); print("FIELD-LEVEL YIELD (of 41 pages x 4 fields = 164 values)"); print("=" * 78)
print(f"{'arm':30} {'name':>7} {'price':>7} {'avail':>7} {'rating':>7} {'total':>9}")
for a, label in ARMS:
    got = {f: sum(1 for r in data[a] if r.get(f)) for f in ("name","price","availability","rating")}
    tot = sum(got.values())
    print(f"{label:30} {got['name']:>7} {got['price']:>7} {got['availability']:>7} {got['rating']:>7} "
          f"{tot:>4}/164 {100*tot/164:>4.0f}%")

json.dump({a: collections.Counter(r["outcome"] for r in data[a]) for a,_ in ARMS},
          open("data/arm_summary.json","w"), indent=2)
