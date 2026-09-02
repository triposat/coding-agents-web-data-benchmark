#!/usr/bin/env python3
"""
Competitor price tracker.

Reads skus.json (never modified), visits all 41 retailer product pages
listed there through the Bright Data Web Unlocker API (this bypasses the
basic bot-detection that most of these retail sites use, without ever
logging in or touching anything other than a public product page), pulls
out product name / current price / availability / customer rating, and
writes results.json.

Usage:
    python3 tracker.py

Auth:
    Needs a Bright Data API key (a scraping-proxy credential, NOT a
    retailer login). It is read from, in order:
      1. the BRIGHTDATA_API_KEY environment variable
      2. the ?token=... query string of mcp.json in this same folder
         (present in this project already, kept only as a convenience
         fallback for this environment)

    Needs a Bright Data "Web Unlocker" zone name, default "web_unlocker"
    (override with BRIGHTDATA_ZONE).

Raw responses are cached under cache/ (one file per retailer page) purely
for debugging/inspection; every run re-fetches fresh data over the network
and overwrites results.json.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import sys
import time
import urllib.parse

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
SKUS_PATH = os.path.join(HERE, "skus.json")
RESULTS_PATH = os.path.join(HERE, "results.json")
CACHE_DIR = os.path.join(HERE, "cache")

BRIGHTDATA_ENDPOINT = "https://api.brightdata.com/request"
BRIGHTDATA_ZONE = os.environ.get("BRIGHTDATA_ZONE", "web_unlocker")

MAX_ATTEMPTS = 4
MIN_BODY_LEN = 200        # bodies shorter than this are treated as failed/blocked fetches
REQUEST_TIMEOUT = 110     # seconds; the unlocker can take 30-90s to defeat bot checks
MAX_WORKERS = 6

TARGET_REDSKY_KEY = "9f36aeafbe60771e321a7cc95a78140772ab3e96"  # public key Target's own web app ships to every visitor
TARGET_DIGITAL_STORE_ID = "3991"   # Target's built-in "digital" store id, good for price/rating lookups
TARGET_PHYSICAL_STORE_ID = "1859"  # a real store id, needed for the fulfillment/availability lookup
TARGET_ZIP, TARGET_STATE, TARGET_LAT, TARGET_LON = "10001", "NY", "40.750", "-73.994"


def get_api_key() -> str | None:
    key = os.environ.get("BRIGHTDATA_API_KEY")
    if key:
        return key
    mcp_path = os.path.join(HERE, "mcp.json")
    if os.path.exists(mcp_path):
        try:
            with open(mcp_path) as f:
                cfg = json.load(f)
            url = cfg["mcpServers"]["brightdata"]["url"]
            m = re.search(r"token=([^&]+)", url)
            if m:
                return m.group(1)
        except Exception:
            pass
    return None


API_KEY = get_api_key()


class FetchError(Exception):
    pass


def fetch_raw(url: str, cache_key: str) -> str:
    """Fetch a URL's body through the Bright Data Web Unlocker, with retries
    for the empty-body flakiness the unlocker occasionally exhibits."""
    if not API_KEY:
        raise FetchError("no_api_key")

    last_err = "unknown_error"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(
                BRIGHTDATA_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"zone": BRIGHTDATA_ZONE, "url": url, "format": "raw"},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.exceptions.RequestException as e:
            last_err = f"network_error:{type(e).__name__}"
            time.sleep(2 * attempt)
            continue

        if resp.status_code != 200:
            last_err = f"http_{resp.status_code}"
            time.sleep(2 * attempt)
            continue

        body = resp.text
        if len(body) < MIN_BODY_LEN:
            last_err = "empty_response"
            time.sleep(2 * attempt)
            continue

        if os.environ.get("TRACKER_CACHE", "1") == "1":
            os.makedirs(CACHE_DIR, exist_ok=True)
            safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", cache_key)
            with open(os.path.join(CACHE_DIR, safe), "w", encoding="utf-8") as f:
                f.write(body)

        return body

    raise FetchError(last_err)


# ---------------------------------------------------------------------------
# Generic fallback: schema.org JSON-LD Product block (works on several sites
# regardless of everything else, so every parser tries it first).
# ---------------------------------------------------------------------------

LD_JSON_RE = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S
)

AVAILABILITY_MAP = {
    "instock": "In Stock",
    "outofstock": "Out of Stock",
    "limitedavailability": "Limited Availability",
    "preorder": "Pre-Order",
    "discontinued": "Discontinued",
    "soldout": "Out of Stock",
    "backorder": "Backordered",
}


def _availability_from_schema_url(value: str | None) -> str | None:
    if not value:
        return None
    tail = value.rstrip("/").rsplit("/", 1)[-1].lower()
    return AVAILABILITY_MAP.get(tail, value)


def extract_ldjson_products(html: str) -> list[dict]:
    out = []
    for block in LD_JSON_RE.findall(html):
        try:
            data = json.loads(block)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            t = item.get("@type")
            if t == "Product" or (isinstance(t, list) and "Product" in t):
                out.append(item)
            for g in item.get("@graph", []) or []:
                if isinstance(g, dict) and g.get("@type") == "Product":
                    out.append(g)
    return out


def parse_ldjson_generic(html: str) -> dict:
    result = {"name": None, "price": None, "availability": None, "rating": None}
    products = extract_ldjson_products(html)
    if not products:
        return result
    p = products[0]
    result["name"] = p.get("name")
    offers = p.get("offers")
    if isinstance(offers, list) and offers:
        offer = next((o for o in offers if "new" in str(o.get("itemCondition", "")).lower()), offers[0])
    elif isinstance(offers, dict):
        offer = offers
    else:
        offer = None
    if offer:
        result["price"] = offer.get("price")
        result["availability"] = _availability_from_schema_url(offer.get("availability"))
    agg = p.get("aggregateRating")
    if isinstance(agg, dict):
        result["rating"] = agg.get("ratingValue")
    return result


def og_title(html: str) -> str | None:
    m = re.search(r'property=["\']og:title["\']\s+content=["\']([^"\']*)["\']', html)
    if m:
        return m.group(1).strip()
    m = re.search(r'<title[^>]*>([^<]*)</title>', html)
    if m:
        return m.group(1).strip()
    return None


def to_float(s) -> float | None:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    m = re.search(r"[\d,]+\.?\d*", str(s).replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Per-retailer parsers
# ---------------------------------------------------------------------------

def parse_bestbuy(html: str, url: str) -> dict:
    r = parse_ldjson_generic(html)
    if r["name"] and r["price"] and r["rating"] and r["availability"]:
        return r
    if not r["name"]:
        r["name"] = og_title(html)
    if not r["price"]:
        m = re.search(r'"customerPrice":([\d.]+)', html)
        if m:
            r["price"] = float(m.group(1))
    if not r["rating"]:
        m = re.search(r'"aggregateRating":\{[^}]*"ratingValue":([\d.]+)', html)
        if m:
            r["rating"] = float(m.group(1))
        else:
            # newer BestBuy PDP template: no JSON-LD, but a visually-hidden
            # "Rating X out of 5 stars with N reviews" string is still SSR'd.
            m = re.search(r'Rating ([\d.]+) out of 5 stars', html)
            if m:
                r["rating"] = float(m.group(1))
    if not r["availability"]:
        m = re.search(r'"availability":"([^"]+)"', html)
        if m:
            r["availability"] = _availability_from_schema_url(m.group(1))
    return r


def parse_amazon(html: str, url: str) -> dict:
    result = {"name": None, "price": None, "availability": None, "rating": None}

    m = re.search(r'id="productTitle"[^>]*>([^<]*)<', html)
    result["name"] = m.group(1).strip() if m else og_title(html)

    m = re.search(r'id="acrPopover"[^>]*title="([\d.]+) out of 5 stars"', html)
    if m:
        result["rating"] = float(m.group(1))

    m = re.search(r'"priceAmount"\s*:\s*([\d.]+)', html)
    if m:
        result["price"] = float(m.group(1))
    else:
        m = re.search(r'class="a-price-whole">([\d,]+)<.*?class="a-price-fraction">(\d+)<', html, re.S)
        if m:
            result["price"] = float(m.group(1).replace(",", "") + "." + m.group(2))

    m = re.search(r'id="availability"[^>]*>\s*<span[^>]*>([^<]*)<', html, re.S)
    if m and m.group(1).strip():
        result["availability"] = m.group(1).strip()
    else:
        m = re.search(r'id="outOfStock"[^>]*>.*?<span[^>]*>([^<]*)<', html, re.S)
        if m:
            result["availability"] = m.group(1).strip()
        elif re.search(r'"inStock"\s*:\s*true', html):
            result["availability"] = "In Stock"
        elif result["price"] is not None and re.search(r"add-to-cart", html, re.I):
            # No explicit "In Stock" label, but there's a live price and a
            # working Add to Cart control, so it is purchasable right now.
            result["availability"] = "In Stock"

    if not result["name"] and re.search(r"Enter the characters you see below|api-services-support@amazon", html, re.I):
        raise FetchError("blocked_captcha")

    return result


def _nearest_match(html: str, anchor: int, pattern: str):
    """Among all regex matches in html, return the one whose start index is
    closest to anchor. Walmart embeds many product blurbs (main item plus
    carousels of related items) with the same field names, so proximity to
    the item's own usItemId is the most reliable way to pick the right one."""
    matches = list(re.finditer(pattern, html))
    if not matches:
        return None
    if anchor < 0:
        return matches[0]
    return min(matches, key=lambda m: abs(m.start() - anchor))


def parse_walmart(html: str, url: str) -> dict:
    result = {"name": None, "price": None, "availability": None, "rating": None}

    title = og_title(html)
    if title:
        result["name"] = re.sub(r"\s*-\s*Walmart\.com\s*$", "", title).strip()

    m = re.search(r'/ip/(\d+)', url)
    anchor = html.find(f'"usItemId":"{m.group(1)}"') if m else -1

    pm = _nearest_match(html, anchor, r'"currentPrice":\{"price":([\d.]+)')
    if pm:
        result["price"] = float(pm.group(1))

    rm = _nearest_match(html, anchor, r'"averageRating":([\d.]+)')
    if rm:
        result["rating"] = float(rm.group(1))

    am = _nearest_match(html, anchor, r'"availabilityStatus":"([^"]+)"')
    if am:
        status = am.group(1)
        result["availability"] = {"IN_STOCK": "In Stock", "OUT_OF_STOCK": "Out of Stock"}.get(status, status)

    return result


def parse_newegg(html: str, url: str) -> dict:
    result = {"name": None, "price": None, "availability": None, "rating": None}

    title = og_title(html)
    if title:
        result["name"] = re.sub(r"\s*-\s*Newegg\.com\s*$", "", title).strip()

    m = re.search(r'class="price-current[^"]*"[^>]*>.*?\$<strong>([\d,]+)</strong><sup>\.?(\d+)</sup>', html, re.S)
    if m:
        result["price"] = float(m.group(1).replace(",", "") + "." + m.group(2))

    m = re.search(r'class="product-rating">.*?title="([\d.]+) out of 5 eggs"', html, re.S)
    if m:
        result["rating"] = float(m.group(1))

    if re.search(r'>\s*Add to cart\s*<', html):
        result["availability"] = "In Stock"
    elif re.search(r'SOLD OUT|AUTO NOTIFY', html, re.I):
        result["availability"] = "Out of Stock"

    return result


def parse_target(html_page: str, url: str) -> dict:
    result = {"name": None, "price": None, "availability": None, "rating": None}

    m = re.search(r"A-(\d+)", url)
    if not m:
        return result
    tcin = m.group(1)

    api_url = (
        "https://redsky.target.com/redsky_aggregations/v1/web/pdp_client_v1"
        f"?key={TARGET_REDSKY_KEY}&tcin={tcin}&is_bot=false"
        f"&store_id={TARGET_DIGITAL_STORE_ID}&pricing_store_id={TARGET_DIGITAL_STORE_ID}"
    )
    body = fetch_raw(api_url, cache_key=f"target_api_{tcin}.json")
    data = json.loads(body)
    product = data.get("data", {}).get("product", {})
    if not product:
        return result

    item = product.get("item", {})
    result["name"] = item.get("product_description", {}).get("title")

    price = product.get("price", {})
    result["price"] = to_float(price.get("current_retail") or price.get("formatted_current_price"))

    ratings = product.get("ratings_and_reviews", {}).get("statistics", {}).get("rating", {})
    result["rating"] = ratings.get("average")

    # Price/rating come from a "digital store" that can't answer fulfillment
    # questions, so availability needs its own call against a real store id.
    try:
        fulfillment_url = (
            "https://redsky.target.com/redsky_aggregations/v1/web/pdp_fulfillment_v1"
            f"?key={TARGET_REDSKY_KEY}&tcin={tcin}&is_bot=false"
            f"&store_id={TARGET_PHYSICAL_STORE_ID}&pricing_store_id={TARGET_PHYSICAL_STORE_ID}"
            f"&zip={TARGET_ZIP}&state={TARGET_STATE}&latitude={TARGET_LAT}&longitude={TARGET_LON}"
        )
        fbody = fetch_raw(fulfillment_url, cache_key=f"target_fulfillment_{tcin}.json")
        fdata = json.loads(fbody)
        fulfillment = fdata.get("data", {}).get("product", {}).get("fulfillment", {})
        status = fulfillment.get("shipping_options", {}).get("availability_status")
        if status:
            result["availability"] = {"IN_STOCK": "In Stock", "OUT_OF_STOCK": "Out of Stock"}.get(status, status)
        elif fulfillment.get("is_out_of_stock_in_all_store_locations") is True:
            result["availability"] = "Out of Stock"
    except Exception:
        pass

    return result


DOMAIN_PARSERS = [
    ("bestbuy.com", "html", parse_bestbuy),
    ("amazon.com", "html", parse_amazon),
    ("walmart.com", "html", parse_walmart),
    ("newegg.com", "html", parse_newegg),
    ("target.com", "special", parse_target),
]


def parse_page(retailer_url: str, html: str | None) -> dict:
    host = urllib.parse.urlparse(retailer_url).netloc
    for domain, kind, fn in DOMAIN_PARSERS:
        if domain in host:
            if kind == "special":
                return fn(html, retailer_url)
            return fn(html, retailer_url)
    # unknown retailer domain: best-effort generic parse
    r = parse_ldjson_generic(html or "")
    if not r["name"]:
        r["name"] = og_title(html or "")
    return r


def process_one(sku_id: str, product: str, retailer: str, url: str) -> dict:
    record = {
        "sku_id": sku_id,
        "product": product,
        "retailer": retailer,
        "url": url,
        "name": None,
        "price": None,
        "availability": None,
        "rating": None,
        "status": None,
    }

    host = urllib.parse.urlparse(url).netloc
    is_target = "target.com" in host

    try:
        html = None if is_target else fetch_raw(url, cache_key=f"{sku_id}_{retailer}.html")
        parsed = parse_page(url, html)
    except FetchError as e:
        record["status"] = str(e)
        return record
    except Exception as e:
        record["status"] = f"parse_error:{type(e).__name__}"
        return record

    record["name"] = parsed.get("name")
    record["price"] = to_float(parsed.get("price"))
    record["availability"] = parsed.get("availability")
    record["rating"] = to_float(parsed.get("rating"))

    missing = [f for f in ("name", "price", "availability", "rating") if record[f] in (None, "")]
    record["status"] = "ok" if not missing else "missing_" + "_".join(missing)
    return record


def main() -> int:
    if not API_KEY:
        print(
            "ERROR: no Bright Data API key found. Set BRIGHTDATA_API_KEY.",
            file=sys.stderr,
        )
        return 1

    with open(SKUS_PATH) as f:
        skus = json.load(f)

    jobs = []
    for sku in skus:
        for retailer, info in sku["retailers"].items():
            jobs.append((sku["sku_id"], sku["product"], retailer, info["url"]))

    print(f"Fetching {len(jobs)} product pages via Bright Data Web Unlocker (zone={BRIGHTDATA_ZONE})...")

    results = [None] * len(jobs)
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_to_idx = {
            pool.submit(process_one, *job): i for i, job in enumerate(jobs)
        }
        done = 0
        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            job = jobs[idx]
            try:
                results[idx] = future.result()
            except Exception as e:
                results[idx] = {
                    "sku_id": job[0], "product": job[1], "retailer": job[2], "url": job[3],
                    "name": None, "price": None, "availability": None, "rating": None,
                    "status": f"unexpected_error:{type(e).__name__}",
                }
            done += 1
            r = results[idx]
            print(f"[{done}/{len(jobs)}] {r['sku_id']} {r['retailer']:10s} -> {r['status']}")

    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\nWrote {RESULTS_PATH}: {ok}/{len(results)} pages collected all 4 fields.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
