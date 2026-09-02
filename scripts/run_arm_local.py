"""Arms 1 and 2: what a coding agent writes when it has no data layer.
Arm 1 = requests-style plain HTTP with a browser UA.
Arm 2 = local headless Playwright (the usual second attempt after arm 1 fails)."""
import sys, json, time, urllib.request, urllib.error
sys.path.insert(0, "scripts")
from extract import classify

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")
skus = json.load(open("data/skus.json"))
TARGETS = [(s["sku_id"], s["product"], r, d["url"])
           for s in skus for r, d in s["retailers"].items()]
print(f"{len(TARGETS)} targets", file=sys.stderr)

def arm1(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "ignore"), None
    except urllib.error.HTTPError as e:
        return e.code, "", None
    except Exception as e:
        return None, "", f"{type(e).__name__}: {e}"

def run(arm):
    rows = []
    if arm == "arm2_local_browser":
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        br = pw.chromium.launch(headless=True)
    for sid, prod, ret, url in TARGETS:
        t0 = time.time()
        if arm == "arm1_plain_http":
            st, body, err = arm1(url)
        else:
            st, body, err = None, "", None
            try:
                ctx = br.new_context(user_agent=UA, locale="en-US")
                pg = ctx.new_page()
                resp = pg.goto(url, timeout=45000, wait_until="domcontentloaded")
                pg.wait_for_timeout(2500)
                st = resp.status if resp else None
                body = pg.content()
                ctx.close()
            except Exception as e:
                err = f"{type(e).__name__}: {str(e)[:120]}"
        outcome, fields = classify(st, body, err)
        row = {"arm": arm, "sku_id": sid, "product": prod, "retailer": ret, "url": url,
               "http_status": st, "elapsed_s": round(time.time()-t0, 2),
               "bytes": len(body), "outcome": outcome, "error": err, **fields}
        open(f"data/payloads/{arm}__{sid}__{ret}.txt","w").write(body or "")
        rows.append(row)
        print(json.dumps({k: row[k] for k in ("arm","sku_id","retailer","http_status","outcome","elapsed_s")}), flush=True)
        time.sleep(1.5)
    if arm == "arm2_local_browser":
        br.close(); pw.stop()
    json.dump(rows, open(f"data/{arm}.json", "w"), indent=2)
    return rows

for arm in ("arm1_plain_http", "arm2_local_browser"):
    rows = run(arm)
    from collections import Counter
    print(f"\n=== {arm} ===", Counter(r["outcome"] for r in rows), file=sys.stderr)
