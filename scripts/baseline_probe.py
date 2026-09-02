"""Baseline reachability probe: plain HTTP, no proxy, no unlocker.
Measures what a coding agent's first-instinct `requests.get` actually gets back.
Low volume: one request per target."""
import json, time, sys
import urllib.request, urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

TARGETS = [
    ("amazon",   "https://www.amazon.com/dp/B0D1XD1ZV3"),
    ("walmart",  "https://www.walmart.com/ip/5689919121"),
    ("bestbuy",  "https://www.bestbuy.com/site/apple-airpods-pro-2/6447382.p?skuId=6447382"),
    ("target",   "https://www.target.com/p/-/A-88451170"),
    ("ebay",     "https://www.ebay.com/itm/335581646339"),
    ("newegg",   "https://www.newegg.com/p/N82E16824012039"),
]

def probe(name, url, with_ua):
    req = urllib.request.Request(url)
    if with_ua:
        req.add_header("User-Agent", UA)
        req.add_header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        req.add_header("Accept-Language", "en-US,en;q=0.9")
    t0 = time.time()
    rec = {"retailer": name, "url": url, "ua": "browser" if with_ua else "python-default"}
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            rec.update(status=r.status, bytes=len(body), elapsed=round(time.time()-t0, 2))
            txt = body[:400000].decode("utf-8", "ignore").lower()
            rec["captcha_marker"] = any(m in txt for m in
                ["captcha", "are you a robot", "verify you are human", "px-captcha",
                 "cf-challenge", "challenge-platform", "unusual traffic", "access denied",
                 "enable javascript and cookies", "bot detection"])
            rec["title"] = (txt.split("<title>")[1].split("</title>")[0].strip()[:120]
                            if "<title>" in txt else "")
    except urllib.error.HTTPError as e:
        rec.update(status=e.code, bytes=0, elapsed=round(time.time()-t0, 2),
                   error=f"HTTPError {e.code} {e.reason}")
    except Exception as e:
        rec.update(status=None, bytes=0, elapsed=round(time.time()-t0, 2),
                   error=f"{type(e).__name__}: {e}")
    return rec

out = []
for with_ua in (False, True):
    for name, url in TARGETS:
        r = probe(name, url, with_ua)
        out.append(r)
        print(json.dumps(r), flush=True)
        time.sleep(2)

json.dump(out, open("data/baseline_probe.json", "w"), indent=2)
