#!/usr/bin/env python3
"""Competitor price tracker: scrapes skus.json product pages, writes results.json,
finds new competitor listings via web search, writes new_listings.json.

Usage: uv run tracker.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).parent
SKUS_PATH = BASE / "skus.json"
RESULTS_PATH = BASE / "results.json"
NEW_LISTINGS_PATH = BASE / "new_listings.json"
RAW_DEBUG_DIR = BASE / ".raw_pages"  # debug copies of scraped pages, safe to delete
ZONE = "web_unlocker"

NON_RETAIL_DOMAINS = {
    "reddit.com", "youtube.com", "facebook.com", "twitter.com", "x.com",
    "instagram.com", "pinterest.com", "wikipedia.org", "quora.com",
    "camelcamelcamel.com", "keepa.com", "slickdeals.net", "medium.com",
    "tiktok.com", "threads.net", "google.com", "yelp.com", "linkedin.com",
    # news / editorial / review outlets — they write about products, they
    # don't sell them
    "cnet.com", "nbcnews.com", "macrumors.com", "engadget.com", "pcworld.com",
    "techreprise.com", "appleinsider.com", "theverge.com", "wired.com",
    "forbes.com", "businessinsider.com", "techradar.com", "tomsguide.com",
    "gizmodo.com", "digitaltrends.com", "laptopmag.com", "zdnet.com",
    "arstechnica.com", "9to5mac.com", "lttlabs.com",
}

# path fragments that indicate a support/editorial page rather than a product listing
NON_LISTING_PATH_HINTS = (
    "/article", "/support", "/blog", "/help", "/forum", "/community",
    "/guide", "/wiki", "/review", "/news", "/press", "/faq", "/deals",
)

# subdomain prefixes that indicate a support/price-history page rather than a store
NON_LISTING_SUBDOMAIN_PREFIXES = ("support.", "prices.", "price.", "reviews.", "blog.")


def sh(cmd, timeout=90):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def scrape_page(url, cache_key):
    """Fetch a URL fresh via bdata (Bright Data Web Unlocker). Returns (markdown_text, error)."""
    RAW_DEBUG_DIR.mkdir(exist_ok=True)
    out_file = RAW_DEBUG_DIR / f"{cache_key}.md"
    try:
        result = sh(["bdata", "scrape", url, "--format", "markdown", "--zone", ZONE, "-o", str(out_file)])
    except subprocess.TimeoutExpired:
        return None, "scrape timeout"
    if result.returncode != 0:
        msg = (result.stderr or result.stdout or "scrape failed").strip()
        msg = msg.splitlines()[-1] if msg else "scrape failed"
        return None, msg[:200]
    if not out_file.exists() or out_file.stat().st_size == 0:
        return None, "empty response"
    return out_file.read_text(errors="replace"), None


def first_h1(text):
    m = re.search(r"^# (?!#)(.+)$", text, re.M)
    return (m.group(1).strip(), m.end()) if m else (None, 0)


def find_price(sub, patterns):
    for pat in patterns:
        m = re.search(pat, sub)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


def find_rating(sub):
    m = re.search(r"([\d.]+)[^\d\n]{0,20}out of 5 stars", sub)
    if m:
        try:
            v = float(m.group(1))
            if 0 <= v <= 5:
                return v
        except ValueError:
            pass
    return None


def find_availability(sub, in_stock_re, out_of_stock_re):
    if re.search(out_of_stock_re, sub, re.I):
        return "Out of Stock"
    if re.search(in_stock_re, sub, re.I):
        return "In Stock"
    return None


def parse_amazon(text):
    name, idx = first_h1(text)
    sub = text[idx:]
    price = find_price(sub, [r"\$([\d,]+\.\d{2})"])
    rating = find_rating(sub)
    availability = None
    avail_re = r"(In Stock|Currently unavailable|Out of Stock|Temporarily out of stock)"
    m = re.search(avail_re, sub) or re.search(avail_re, text)
    if m:
        availability = "Out of Stock" if "unavailable" in m.group(1).lower() or "out of stock" in m.group(1).lower() else "In Stock"
    elif re.search(r"Add to Cart|Buy Now", sub) or re.search(r"Add to Cart|Buy Now", text):
        availability = "In Stock"
    elif price is not None:
        # Amazon shows a price/buy box only for purchasable listings; an
        # out-of-stock item shows "Currently unavailable" instead of a price.
        availability = "In Stock"
    return name, price, availability, rating


def parse_bestbuy(text):
    name, idx = first_h1(text)
    if name is None:
        # some listings (e.g. discontinued items) render without a markdown H1;
        # fall back to the <title>-derived first line, stripping the site suffix.
        first_line = text.strip().splitlines()[0].strip() if text.strip() else ""
        name = re.sub(r"\s*-\s*Best Buy\s*$", "", first_line).strip() or None
    sub = text[idx:]
    # The "$X.XX$XXXXX" concatenated form is Best Buy's buy-box price render.
    # When it appears exactly once it's reliable; multiple hits mean we've
    # landed on a "similar items" deals carousel instead, so fall back to the
    # seller price range (or a bare price) rather than trusting the first hit.
    concat_matches = re.findall(r"\$([\d,]+\.\d{2})\$\d+", sub)
    if len(concat_matches) == 1:
        price = float(concat_matches[0].replace(",", ""))
    else:
        price = find_price(sub, [r"\$([\d,]+\.\d{2})\s*-\s*\$[\d,]+\.\d{2}", r"\$([\d,]+\.\d{2})"])
    m = re.search(r"Rating ([\d.]+) out of 5 stars", sub)
    rating = float(m.group(1)) if m else find_rating(sub)
    if re.search(r"no longer available", text, re.I):
        availability = "Discontinued / Unavailable"
    else:
        availability = find_availability(sub, r"Add to Cart|Pickup|Shipping", r"Sold Out")
    return name, price, availability, rating


def parse_target(text):
    name, idx = first_h1(text)
    sub = text[idx:]
    price = find_price(sub, [r"\$([\d,]+\.\d{2})"])
    rating = find_rating(sub)
    availability = find_availability(sub, r"Add to cart|Preorder", r"Sold out|Out of stock")
    return name, price, availability, rating


def parse_walmart(text):
    name, idx = first_h1(text)
    sub = text[idx:]
    price = find_price(sub, [r"Current price is USD\$([\d,]+\.\d{2})", r"\$([\d,]+\.\d{2})"])
    rating = find_rating(sub)
    availability = find_availability(sub, r"Add to cart", r"Out of stock")
    return name, price, availability, rating


def parse_newegg(text):
    # Newegg's price/rating widgets are loaded client-side after page load and are
    # not present in the static unlocker response, so those two fields stay null.
    name, idx = first_h1(text)
    sub = text[idx:]
    availability = find_availability(sub, r"Add to cart", r"Sold Out|Out of stock")
    return name, None, availability, None


PARSERS = {
    "amazon": parse_amazon,
    "bestbuy": parse_bestbuy,
    "target": parse_target,
    "walmart": parse_walmart,
    "newegg": parse_newegg,
}


def collect_results(skus):
    results = []
    total = sum(len(p["retailers"]) for p in skus)
    n = 0
    for product in skus:
        sku_id = product["sku_id"]
        product_name = product["product"]
        for retailer, info in product["retailers"].items():
            n += 1
            url = info["url"]
            print(f"[{n}/{total}] {sku_id} / {retailer}: {url}", file=sys.stderr)
            text, err = scrape_page(url, f"{sku_id}_{retailer}")
            record = {
                "sku_id": sku_id,
                "product": product_name,
                "retailer": retailer,
                "url": url,
                "name": None,
                "price": None,
                "availability": None,
                "rating": None,
                "status": None,
            }
            if err:
                record["status"] = f"scrape failed: {err}"
                results.append(record)
                continue
            parser = PARSERS.get(retailer)
            if not parser:
                record["status"] = f"no parser for retailer '{retailer}'"
                results.append(record)
                continue
            try:
                name, price, availability, rating = parser(text)
            except Exception as e:
                record["status"] = f"parse error: {e}"[:200]
                results.append(record)
                continue
            record["name"] = name
            record["price"] = price
            record["availability"] = availability
            record["rating"] = rating
            missing = [k for k in ("name", "price", "availability", "rating") if record[k] is None]
            record["status"] = "ok" if not missing else "missing: " + ", ".join(missing)
            results.append(record)
    return results


def existing_domains_for(product):
    domains = set()
    for info in product["retailers"].values():
        domains.add(urlparse(info["url"]).netloc.replace("www.", ""))
    return domains


def search_new_listings(skus):
    listings = []
    for product in skus:
        sku_id = product["sku_id"]
        product_name = product["product"]
        print(f"searching for new listings: {sku_id} {product_name}", file=sys.stderr)
        existing = existing_domains_for(product)
        query = f"{product_name} price"
        out_file = RAW_DEBUG_DIR / f"{sku_id}_search.json"
        RAW_DEBUG_DIR.mkdir(exist_ok=True)
        try:
            result = sh(["bdata", "search", query, "--type", "web", "--country", "us",
                         "--json", "-o", str(out_file)])
        except subprocess.TimeoutExpired:
            continue
        if result.returncode != 0 or not out_file.exists():
            continue
        try:
            data = json.loads(out_file.read_text())
        except json.JSONDecodeError:
            continue
        organic = data.get("organic", [])
        seen_domains = set()
        found = []
        for item in organic:
            link = item.get("link")
            title = item.get("title")
            if not link or not link.startswith("http"):
                continue
            parsed = urlparse(link)
            domain = parsed.netloc.replace("www.", "")
            if domain in existing or domain in seen_domains:
                continue
            if any(domain == b or domain.endswith("." + b) for b in NON_RETAIL_DOMAINS):
                continue
            if any(domain.startswith(p) for p in NON_LISTING_SUBDOMAIN_PREFIXES):
                continue
            path_lower = parsed.path.lower()
            if any(hint in path_lower for hint in NON_LISTING_PATH_HINTS):
                continue
            seen_domains.add(domain)
            found.append({"retailer": domain, "url": link, "title": title})
            if len(found) >= 5:
                break
        listings.append({
            "sku_id": sku_id,
            "product": product_name,
            "new_listings": found,
        })
    return listings


def main():
    skus = json.loads(SKUS_PATH.read_text())

    print("=== Scraping product pages ===", file=sys.stderr)
    results = collect_results(skus)
    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    ok_count = sum(1 for r in results if r["status"] == "ok")
    print(f"Wrote {RESULTS_PATH.name}: {ok_count}/{len(results)} pages fully collected", file=sys.stderr)

    print("=== Searching for new competitor listings ===", file=sys.stderr)
    listings = search_new_listings(skus)
    NEW_LISTINGS_PATH.write_text(json.dumps(listings, indent=2))
    print(f"Wrote {NEW_LISTINGS_PATH.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
