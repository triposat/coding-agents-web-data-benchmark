#!/usr/bin/env python3
"""Competitor price tracker.

Reads skus.json (41 fixed retailer product pages across 10 products), scrapes
each page through the Bright Data Web Unlocker MCP (scrape_as_markdown tool),
extracts product name / price / availability / rating, and writes
results.json. Also runs a web search per product to find up to 5 additional
retailer listings not already in skus.json (new_listings.json).

Usage:
    python3 tracker.py

Requires .cursor/mcp.json (or mcp.json) in this directory with a "brightdata"
MCP server entry. No other dependencies (stdlib only).
"""
import json
import os
import re
import sys
import time
import collections
import pathlib
import urllib.request
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parent
SKUS_PATH = ROOT / "skus.json"
RESULTS_PATH = ROOT / "results.json"
NEW_LISTINGS_PATH = ROOT / "new_listings.json"
LOG_PATH = ROOT / "tracker_log.txt"

# ------------------------------------------------------------------
# Bright Data MCP client (minimal Streamable-HTTP JSON-RPC client)
# ------------------------------------------------------------------

def _load_mcp_url():
    for p in (ROOT / ".cursor" / "mcp.json", ROOT / "mcp.json"):
        if p.exists():
            cfg = json.loads(p.read_text())
            return cfg["mcpServers"]["brightdata"]["url"]
    raise SystemExit("No .cursor/mcp.json or mcp.json with a 'brightdata' MCP server found.")

MCP_URL = _load_mcp_url()
_session = {"id": None}


def _rpc(method, params=None, notify=False, timeout=180):
    body = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        body["params"] = params
    if not notify:
        body["id"] = 1
    req = urllib.request.Request(MCP_URL, data=json.dumps(body).encode())
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    req.add_header("MCP-Protocol-Version", "2025-06-18")
    if _session["id"]:
        req.add_header("Mcp-Session-Id", _session["id"])
    with urllib.request.urlopen(req, timeout=timeout) as r:
        sid = r.headers.get("Mcp-Session-Id")
        if sid:
            _session["id"] = sid
        raw = r.read().decode("utf-8", "ignore")
    if notify:
        return None
    for line in raw.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    return json.loads(raw) if raw.strip() else None


def mcp_init():
    log("Connecting to Bright Data MCP (first call can take a couple of minutes to warm up)...")
    _rpc("initialize", {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "price-tracker", "version": "1.0"},
    }, timeout=200)
    _rpc("notifications/initialized", {}, notify=True)
    log("MCP session ready: %s" % _session["id"])


def call_tool(name, arguments, timeout=170):
    """Call an MCP tool, return (text, error_str_or_None).

    On error (RPC-level error, or the tool's own isError flag), `text` is
    always "" so a failure message can never be mistaken for scraped page
    content by the extractor.
    """
    try:
        r = _rpc("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)
    except Exception as e:
        return "", f"{type(e).__name__}: {str(e)[:150]}"
    res = (r or {}).get("result", {}) or {}
    rpc_err = (r or {}).get("error")
    content = res.get("content", [])
    text = content[0].get("text", "") if content else ""
    if "_BEGIN=====" in text:
        text = text.split("_BEGIN=====", 1)[1].rsplit("=====UNTRUSTED", 1)[0].strip()
    if rpc_err:
        return "", json.dumps(rpc_err)[:150]
    if res.get("isError"):
        return "", (text or "tool reported isError").strip()[:150]
    return text, None


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


# ------------------------------------------------------------------
# Field extraction (product name / price / rating / availability)
# from a scrape_as_markdown payload. Price takes the most frequently
# repeated currency token on the page (buybox/header/cart all repeat
# the real price; decoys like protection plans appear once or twice).
# ------------------------------------------------------------------

CHALLENGE = [
    "robot or human", "are you a human", "access denied", "verify you are human",
    "enable javascript and cookies to continue", "unusual traffic", "captcha",
    "request blocked", "pardon our interruption", "bot detection",
    "checking your browser", "attention required",
]

PRICE_TOK = re.compile(r"\$\s?([0-9][0-9,]{0,6}\.[0-9]{2})")
RATING_RX = [
    re.compile(r'"ratingValue"\s*:\s*"?([0-5](?:\.[0-9])?)'),
    re.compile(r'([0-5](?:\.[0-9])?)\s*out of\s*5'),
]
AVAIL_RULES = [
    (re.compile(r"\bcurrently unavailable\b", re.I), "OutOfStock"),
    (re.compile(r"\bout of stock\b", re.I), "OutOfStock"),
    (re.compile(r"\bsold out\b", re.I), "OutOfStock"),
    (re.compile(r"\bpre-?order\b", re.I), "PreOrder"),
    (re.compile(r"\bback-?order(?:ed)?\b", re.I), "BackOrder"),
    (re.compile(r"\bin stock\b", re.I), "InStock"),
    (re.compile(r"\badd to cart\b", re.I), "InStock"),
    (re.compile(r"\badd to bag\b", re.I), "InStock"),
]


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
    for rx, v in AVAIL_RULES:
        if rx.search(text):
            return v
    return None


RETRYABLE = {"rate_limited", "blocked_challenge", "blocked_empty", "timeout", "fetch_error"}


def classify(text, err):
    """-> (status, fields) where status is 'ok' or a short reason string."""
    fields = {"name": None, "price": None, "availability": None, "rating": None}
    if err and not text:
        e = err.lower()
        if "timeout" in e:
            return "timeout", fields
        return "fetch_error", fields
    if not text or not text.strip():
        return "blocked_empty", fields
    low = text.lower()
    if "global adaptive rate limit" in low:
        return "rate_limited", fields
    if any(c in low[:4000] for c in CHALLENGE):
        return "blocked_challenge", fields
    fields["name"] = title_of(text)
    fields["price"] = price_of(text)
    fields["availability"] = avail_of(text)
    fields["rating"] = rating_of(text)
    if fields["name"] and fields["price"]:
        return "ok", fields
    if fields["name"]:
        return "no_price_found", fields
    return "no_data_found", fields


def fetch_page(url, max_attempts=3):
    text, err, status, fields = "", None, None, None
    for attempt in range(1, max_attempts + 1):
        text, err = call_tool("scrape_as_markdown", {"url": url}, timeout=170)
        status, fields = classify(text, err)
        if status not in RETRYABLE:
            return status, fields
        wait = 4 * attempt
        log(f"  retry {attempt}/{max_attempts - 1 if attempt < max_attempts else attempt} "
            f"after status={status} (sleeping {wait}s)")
        time.sleep(wait)
    return status, fields


# ------------------------------------------------------------------
# New-listings discovery via search_engine
# ------------------------------------------------------------------

NON_RETAIL_DOMAINS = {
    "youtube.com", "reddit.com", "wikipedia.org", "facebook.com", "instagram.com",
    "twitter.com", "x.com", "pinterest.com", "quora.com", "nytimes.com", "forbes.com",
    "theverge.com", "wired.com", "cnet.com", "techradar.com", "engadget.com",
    "tomsguide.com", "pcmag.com", "rtings.com", "consumerreports.org",
    "bestproducts.com", "businessinsider.com", "gizmodo.com", "medium.com",
    "blogspot.com", "google.com", "bing.com", "yahoo.com", "androidcentral.com",
    "digitaltrends.com", "howtogeek.com", "lifewire.com", "arstechnica.com",
    "reviewgeek.com", "trustpilot.com", "consumeraffairs.com", "sitejabber.com",
    "reviews.com", "goodhousekeeping.com", "popsci.com", "laptopmag.com",
    "9to5mac.com", "9to5google.com", "macrumors.com", "slickdeals.net",
    "dealnews.com", "capitaloneshopping.com", "honey.com", "camelcamelcamel.com",
    "gsmarena.com", "notebookcheck.net", "ign.com", "kotaku.com", "polygon.com",
    "gamespot.com", "linkedin.com", "tiktok.com", "threads.net",
    # price-comparison engines / classifieds / forums, not retailers themselves
    "pricerunner.com", "akakce.com", "cimri.com", "toppreise.ch", "sahibinden.com",
    "alibaba.com", "electronics.alibaba.com", "pricehistory.app", "epey.com",
    "pricespy.co.uk", "idealo.com", "idealo.de", "shopping.google.com",
    "kelkoo.com", "geizhals.de", "billiger.de", "skroutz.gr",
}


def domain_of(url):
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1).lower() if m else ""


def search_new_listings(product, existing_domains, limit=5):
    text, err = call_tool("search_engine", {
        "query": f"buy {product} price",
        "engine": "google",
    }, timeout=170)
    if err and not text:
        return [], err
    organic = []
    try:
        j = json.loads(text)
        if isinstance(j, list):
            j = j[0] if j else {}
        organic = j.get("organic") or (j.get("result") or {}).get("organic") or []
    except Exception:
        # fall back to scanning raw text for URLs if it wasn't JSON
        organic = [{"link": u, "title": None} for u in re.findall(r'https?://[^\s")\]]+', text or "")]
    seen_domains = set(existing_domains)
    out = []
    for item in organic:
        link = (item.get("link") or "").strip()
        if not link:
            continue
        dom = domain_of(link)
        base_dom = ".".join(dom.split(".")[-2:]) if dom else ""
        if not dom or dom in seen_domains or base_dom in seen_domains:
            continue
        if base_dom in NON_RETAIL_DOMAINS or dom in NON_RETAIL_DOMAINS:
            continue
        seen_domains.add(dom)
        seen_domains.add(base_dom)
        out.append({"url": link, "title": item.get("title"), "domain": dom})
        if len(out) >= limit:
            break
    return out, None


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():
    if LOG_PATH.exists():
        LOG_PATH.unlink()
    skus = json.loads(SKUS_PATH.read_text())
    targets = []
    for s in skus:
        for retailer, d in s["retailers"].items():
            targets.append((s["sku_id"], s["product"], retailer, d["url"]))
    log(f"Loaded {len(skus)} products / {len(targets)} retailer pages from skus.json")

    mcp_init()

    # --- 1) scrape all retailer pages ---
    results = []
    for i, (sku_id, product, retailer, url) in enumerate(targets, 1):
        t0 = time.time()
        status, fields = fetch_page(url)
        el = round(time.time() - t0, 1)
        row = {
            "sku_id": sku_id,
            "product": product,
            "retailer": retailer,
            "url": url,
            "name": fields["name"],
            "price": fields["price"],
            "availability": fields["availability"],
            "rating": fields["rating"],
            "status": status,
        }
        results.append(row)
        log(f"[{i}/{len(targets)}] {sku_id} {retailer:8} status={status:16} "
            f"name={'yes' if fields['name'] else 'no':3} price={fields['price']} "
            f"({el}s)")
        RESULTS_PATH.write_text(json.dumps(results, indent=2))
        time.sleep(1)

    all_four = sum(1 for r in results
                   if r["name"] and r["price"] and r["availability"] and r["rating"])
    ok_count = sum(1 for r in results if r["status"] == "ok")
    log(f"Done scraping. status=ok: {ok_count}/{len(results)}  "
        f"all four fields present: {all_four}/{len(results)}")

    # --- 2) new listings per product ---
    new_listings = []
    for s in skus:
        existing_domains = set()
        for retailer, d in s["retailers"].items():
            existing_domains.add(domain_of(d["url"]))
        found, err = search_new_listings(s["product"], existing_domains, limit=5)
        new_listings.append({
            "sku_id": s["sku_id"],
            "product": s["product"],
            "new_retailers": found,
            "error": err,
        })
        log(f"new_listings {s['sku_id']}: found {len(found)} candidate retailer(s)"
            + (f" (error: {err})" if err else ""))
        NEW_LISTINGS_PATH.write_text(json.dumps(new_listings, indent=2))
        time.sleep(1)

    log("All done.")
    log(f"FINAL: {all_four}/{len(results)} pages had all four fields collected "
        f"({ok_count}/{len(results)} status=ok).")


if __name__ == "__main__":
    main()
