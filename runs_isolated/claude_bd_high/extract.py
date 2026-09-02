#!/usr/bin/env python3
"""
Turn raw scraped page content into results.json.

Usage:
    python3 extract.py [scraped_content.json]

Input (scraped_content.json): a JSON array of {"url": ..., "content": ...}
objects, one per product page, where "content" is the markdown/text body
returned by Bright Data's scraper for that URL (empty string if the page
could not be retrieved after retries).

Output (results.json, written next to this script): a JSON array with one
element per (sku, retailer) pair from skus.json, each carrying sku_id,
product, retailer, url, name, price, availability, rating, status.

This script is pure text-processing - it does no network access itself.
Scraping is done by the Bright Data MCP tools from within a Claude Code
session (see README.md for the single rerun command); this script is
invoked at the end of that session to turn the scraped content into the
final results.json.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

WORKDIR = Path(__file__).resolve().parent
CONTENT_FILE = Path(sys.argv[1]) if len(sys.argv) > 1 else WORKDIR / "scraped_content.json"

skus = json.load(open(WORKDIR / "skus.json"))

all_items = json.load(open(CONTENT_FILE))
content_map = {it["url"]: it.get("content", "") for it in all_items}


def clean_num(s):
    return s.replace(",", "") if s else s


def extract_amazon(c):
    lines = c.strip().split("\n")
    title_line = next((l for l in lines if l.strip()), "")
    name = title_line.strip()
    if name.startswith("Amazon.com:"):
        name = name[len("Amazon.com:"):].strip()
    if " : " in name:
        name = name.rsplit(" : ", 1)[0].strip()

    price = None
    m = re.search(r'"displayPrice":"\$([\d,]+\.\d{2})"', c)
    if m:
        price = float(clean_num(m.group(1)))

    rating = None
    m = re.search(r'\[([\d.]+) _[\d.]+ out of 5 stars_\]', c)
    if m:
        rating = float(m.group(1))

    availability = None
    if re.search(r'currently unavailable', c, re.I):
        availability = "Out of Stock"
    elif re.search(r'temporarily out of stock', c, re.I):
        availability = "Out of Stock"
    elif re.search(r'\bIn Stock\b', c):
        availability = "In Stock"

    return name or None, price, availability, rating


def extract_walmart(c):
    m = re.search(r'\n# (.+)\n', c)
    name = m.group(1).strip() if m else None

    rating = None
    m = re.search(r'([\d.]+) out of 5 stars', c)
    if m:
        rating = float(m.group(1))

    price = None
    m = re.search(r'Current price is USD(?:Now)?\s*\$([\d,.]+)', c)
    if m:
        price = float(clean_num(m.group(1)))

    availability = None
    if re.search(r'out of stock', c, re.I):
        availability = "Out of Stock"
    elif "Add to cart" in c:
        availability = "In Stock"

    return name, price, availability, rating


def extract_target(c):
    m = re.search(r'\n# (.+)\n', c)
    name = m.group(1).strip() if m else None

    rating = None
    rating_match = re.search(r'([\d.]+) out of 5 stars', c)
    if rating_match:
        rating = float(rating_match.group(1))

    price = None
    m = re.search(r'\$([\d,.]+) reg \$[\d,.]+', c)
    if m:
        price = float(clean_num(m.group(1)))
    elif rating_match:
        window = c[rating_match.end(): rating_match.end() + 400]
        m2 = re.search(r'\$([\d,.]+)', window)
        if m2:
            price = float(clean_num(m2.group(1)))

    availability = None
    if re.search(r'\bOut of stock\b', c):
        availability = "Out of Stock"
    elif "Add to cart" in c:
        availability = "In Stock"

    return name, price, availability, rating


def extract_newegg(c):
    m = re.search(r'\n# (.+)\n', c)
    name = m.group(1).strip() if m else None

    idx = c.find("Add to cart")
    price = None
    if idx != -1:
        matches = list(re.finditer(r'\$\*\*([\d,]+)\*\*\.(\d{2})', c[:idx]))
        if matches:
            m = matches[-1]
            price = float(clean_num(m.group(1)) + "." + m.group(2))

    availability = "In Stock" if idx != -1 else None
    if re.search(r'out of stock', c, re.I):
        availability = "Out of Stock"

    rating = None  # Newegg renders its star rating as an image sprite; not present in scraped markdown

    return name, price, availability, rating


def extract_bestbuy(c):
    m = re.search(r'\n([^\n]+)\n\nModel:', c)
    name = m.group(1).strip() if m else None

    rating = None
    m = re.search(r'Rating ([\d.]+) out of 5 stars with ([\d,]+) reviews', c)
    if m:
        rating = float(m.group(1))

    price = None
    m = re.search(r'\$([\d,]+\.\d{2})\$\d+', c)
    if m:
        price = float(clean_num(m.group(1)))

    availability = None
    if re.search(r'no longer available', c, re.I):
        availability = "Discontinued / no longer available new"
    elif price is not None or "Add to cart" in c:
        availability = "In Stock"

    return name, price, availability, rating


DOMAIN_EXTRACTORS = {
    "www.amazon.com": extract_amazon,
    "www.walmart.com": extract_walmart,
    "www.target.com": extract_target,
    "www.newegg.com": extract_newegg,
    "www.bestbuy.com": extract_bestbuy,
}

results = []
for sku in skus:
    for retailer, info in sku["retailers"].items():
        url = info["url"]
        sku_id = sku["sku_id"]
        product = sku["product"]
        content = content_map.get(url, "")
        domain = urlparse(url).netloc
        extractor = DOMAIN_EXTRACTORS[domain]

        if not content or not content.strip():
            results.append({
                "sku_id": sku_id, "product": product, "retailer": retailer, "url": url,
                "name": None, "price": None, "availability": None, "rating": None,
                "status": "page_returned_empty_content_after_retries",
            })
            continue

        name, price, availability, rating = extractor(content)
        missing = [f for f, v in [("name", name), ("price", price), ("availability", availability), ("rating", rating)] if v is None]
        status = "ok" if not missing else "partial: missing " + ",".join(missing)

        results.append({
            "sku_id": sku_id, "product": product, "retailer": retailer, "url": url,
            "name": name, "price": price, "availability": availability, "rating": rating,
            "status": status,
        })

json.dump(results, open(WORKDIR / "results.json", "w"), indent=2)

ok_count = sum(1 for r in results if r["status"] == "ok")
print(f"Total: {len(results)}  OK (all 4 fields): {ok_count}")
for r in results:
    if r["status"] != "ok":
        print(r["sku_id"], r["retailer"], "->", r["status"], "| name=", r["name"], "price=", r["price"], "avail=", r["availability"], "rating=", r["rating"])
