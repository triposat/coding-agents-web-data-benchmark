"""At which layer does a site refuse a non-browser client?

Three clients, same public page, same machine, same minute:
  urllib   HTTP/1.1, no browser fingerprint at all
  curl     HTTP/2, but a curl HTTP/2 fingerprint
  chromium HTTP/2 with a real Chrome fingerprint

The pattern across the three localises the check:
  all three fail            -> refusing on IP, geography or something upstream
  urllib+curl fail, cx ok   -> keying on the transport fingerprint
  all three reach HTML,
    but curl gets a challenge -> page-level check, JS or cookie
  all three clean           -> no discrimination at this layer
"""
import json, re, subprocess, sys, time, urllib.error, urllib.request
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")
SITES = [
    ("amazon",       "https://www.amazon.com/s?k=usb+c+cable"),
    ("walmart",      "https://www.walmart.com/browse/electronics/3944"),
    ("bestbuy",      "https://www.bestbuy.com/site/searchpage.jsp?st=ssd"),
    ("target",       "https://www.target.com/c/electronics/-/N-5xtg6"),
    ("newegg",       "https://www.newegg.com/p/pl?d=ssd"),
    ("etsy",         "https://www.etsy.com/search?q=mug"),
    ("ebay",         "https://www.ebay.com/sch/i.html?_nkw=ssd"),
    ("homedepot",    "https://www.homedepot.com/b/Appliances/N-5yc1vZbv1w"),
    ("booking",      "https://www.booking.com/searchresults.html?ss=Paris"),
    ("indeed",       "https://www.indeed.com/jobs?q=python"),
    ("zillow",       "https://www.zillow.com/homes/Austin,-TX_rb/"),
    ("ticketmaster", "https://www.ticketmaster.com/discover/concerts"),
    ("glassdoor",    "https://www.glassdoor.com/Job/index.htm"),
    ("crunchbase",   "https://www.crunchbase.com/discover/organization.companies"),
    ("yelp",         "https://www.yelp.com/search?find_desc=coffee"),
]
CHALLENGE = re.compile(r"captcha|are you a human|robot or human|verify you are|"
                       r"access denied|unusual traffic|enable javascript to continue|"
                       r"press & hold|challenge-platform|areyouahuman|blocked", re.I)
def classify(status, body, err):
    if err:
        e = err.lower()
        if "http2" in e or "connection reset" in e or "protocol" in e: return "transport_reset"
        if "timed out" in e or "timeout" in e: return "timeout"
        if "403" in e: return "http_403"
        if "429" in e: return "http_429"
        return f"error"
    if status and status >= 400: return f"http_{status}"
    if body and CHALLENGE.search(body[:200000]): return "challenge_page"
    if body and len(body) > 20000: return "ok"
    return "thin_body"
def via_urllib(u):
    t0 = time.time()
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA, "Accept-Encoding": "identity"}), timeout=30)
        return classify(r.status, r.read().decode("utf-8", "ignore"), None), round(time.time()-t0, 1)
    except urllib.error.HTTPError as e:
        return classify(e.code, "", None), round(time.time()-t0, 1)
    except Exception as e:
        return classify(None, "", f"{type(e).__name__}: {e}"), round(time.time()-t0, 1)
def via_curl(u):
    t0 = time.time()
    # --compressed so gzip is decoded; bytes not text, because some bodies are not utf-8
    p = subprocess.run(["curl", "-sS", "--compressed", "--max-time", "30", "-A", UA,
                        "-w", "\n%{http_code}", u], capture_output=True)
    if p.returncode != 0:
        return classify(None, "", p.stderr.decode("utf-8", "ignore")), round(time.time()-t0, 1)
    out = p.stdout.decode("utf-8", "ignore")
    body, _, code = out.rpartition("\n")
    return classify(int(code.strip() or 0), body, None), round(time.time()-t0, 1)
def main():
    from playwright.sync_api import sync_playwright
    rows = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        for name, url in SITES:
            u_out, u_s = via_urllib(url)
            c_out, c_s = via_curl(url)
            t0 = time.time()
            try:
                pg = b.new_page(); r = pg.goto(url, timeout=45000, wait_until="domcontentloaded")
                pg.wait_for_timeout(1500)
                x_out = classify(r.status if r else None, pg.content(), None)
                pg.close()
            except Exception as e:
                x_out = classify(None, "", f"{type(e).__name__}: {e}")
            x_s = round(time.time()-t0, 1)
            rows.append({"site": name, "url": url, "urllib": u_out, "curl": c_out,
                         "chromium": x_out, "secs": {"urllib": u_s, "curl": c_s, "chromium": x_s}})
            print(f"  {name:13} urllib={u_out:16} curl={c_out:16} chromium={x_out}", flush=True)
        b.close()
    json.dump(rows, open("data/refusal_layer.json", "w"), indent=2)
if __name__ == "__main__":
    main()
