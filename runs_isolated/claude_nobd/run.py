#!/usr/bin/env python3
"""
Competitor price tracker — single-command runner.

Usage:
    python3 run.py

Re-fetches all 41 product pages listed in skus.json, writes:
  - results.json        (price/availability/rating/name per page)
  - new_listings.json   (up to 5 new competitor URLs per product, via web search)

dashboard.html is static and reads results.json at load time — no rebuild needed.

Requires the `bdata` CLI (Bright Data) to be authenticated (`bdata login` / API key
already configured, per repo conventions). Only public product pages are fetched;
no login or credentials are used against any retailer site.
"""
import json
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "raw")
SEARCH = os.path.join(BASE, "search")
os.makedirs(RAW, exist_ok=True)
os.makedirs(SEARCH, exist_ok=True)

PIPE_MAP = {"amazon": "amazon_product", "walmart": "walmart_product", "bestbuy": "bestbuy_products"}
SCRAPE_RETAILERS = {"target", "newegg"}

# Domains already covered by skus.json — always excluded from new_listings.json
KNOWN_DOMAINS = {"amazon.com", "walmart.com", "bestbuy.com", "target.com", "newegg.com"}
# Non-retailer noise to skip when mining search results for new listings
BLOCKLIST_SUBSTRINGS = [
    "reddit.com", "youtube.com", "wikipedia.org", "camelcamelcamel.com",
    "support.apple.com", "service.anker.com", "mysupport.razer.com",
    "rtings.com", "engadget.com", "cnet.com", "mashable.com", "thepointsguy.com",
    "techreprise.com", "google.com", "bing.com",
]


def run(cmd, timeout=900):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)


def to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"[\d,]+\.?\d*", v.replace(",", ""))
        if m:
            try:
                return float(m.group())
            except ValueError:
                return None
    return None


# ---------- structured pipeline parsers (amazon / walmart / bestbuy) ----------

def parse_amazon(d):
    name = d.get("title")
    price = to_float(d.get("final_price") if d.get("final_price") is not None else d.get("price"))
    availability = d.get("availability")
    if availability is None and d.get("is_available") is not None:
        availability = "In Stock" if d["is_available"] else "Out of Stock"
    return name, price, availability, d.get("rating")


def parse_walmart(d):
    name = d.get("product_name")
    price = to_float(d.get("final_price") if d.get("final_price") is not None else d.get("price"))
    availability = d.get("availability") or ("in_stock" if d.get("is_available") else "out_of_stock")
    return name, price, availability, d.get("rating")


def parse_bestbuy(d):
    name = d.get("title")
    price = to_float(d.get("final_price") if d.get("final_price") is not None else d.get("price"))
    availability = d.get("availability_new") or d.get("availability")
    if isinstance(availability, list):
        availability = ", ".join(a.get("availability_name", "") for a in availability if isinstance(a, dict)) or None
    return name, price, availability, d.get("rating")


STRUCT_PARSERS = {"amazon": parse_amazon, "walmart": parse_walmart, "bestbuy": parse_bestbuy}


def fetch_structured(retailer, url, out_path, retries=2):
    pipe = PIPE_MAP[retailer]
    for attempt in range(retries + 1):
        r = run(f'bdata pipelines {pipe} "{url}" -o "{out_path}" --json')
        if os.path.exists(out_path):
            try:
                data = json.load(open(out_path))
                rec = data[0] if isinstance(data, list) and data else data
                if isinstance(rec, dict) and not rec.get("error"):
                    return rec, None
                err = rec.get("error") if isinstance(rec, dict) else "empty response"
            except Exception as e:
                err = f"invalid json: {e}"
        else:
            err = (r.stderr or r.stdout or "no output").strip()[-300:]
        if attempt < retries:
            time.sleep(3)
    return None, err


# ---------- markdown parsers (target / newegg, via bdata scrape) ----------

def parse_target_markdown(text):
    name = None
    m = re.search(r"^# (.+)$", text, re.M)
    if m:
        name = m.group(1).strip()

    rating = None
    m = re.search(r"(\d\.\d+) out of 5 stars", text)
    if m:
        rating = float(m.group(1))

    price = None
    # first $ amount after the H1 product title
    if m := re.search(r"^# .+$", text, re.M):
        tail = text[m.end():]
        pm = re.search(r"\$([\d,]+\.\d{2})", tail)
        if pm:
            price = to_float(pm.group(1))
            window = tail[pm.end(): pm.end() + 400]
            if re.search(r"sold out|out of stock", window, re.I):
                availability = "Out of Stock"
            elif re.search(r"pickup|delivery|shipping|arrives by|ready within", window, re.I):
                availability = "In Stock"
            else:
                availability = None
        else:
            availability = None
    else:
        availability = None

    return name, price, availability, rating


def parse_newegg_markdown(text):
    name = None
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    name = re.sub(r"\s*-\s*Newegg\.com\s*$", "", first_line).strip() or None

    cart_idx = text.find("Add to cart")
    search_region = text[: cart_idx] if cart_idx != -1 else text
    prices = [to_float(p) for p in re.findall(r"\$\*\*([\d,]+)\*\*\.(\d{2})", search_region)]
    # re.findall with two groups returns tuples; rebuild properly
    price_matches = re.findall(r"\$\*\*([\d,]+)\*\*\.(\d{2})", search_region)
    price = None
    if price_matches:
        whole, cents = price_matches[-1]
        price = to_float(f"{whole}.{cents}")

    availability = "In Stock" if cart_idx != -1 else None
    if re.search(r"out of stock|sold out", text, re.I):
        availability = "Out of Stock"

    rating = None
    m = re.search(r"Customer Reviews of[^\n]*\n\n(.+?)\n", text)
    if m and "no reviews yet" not in m.group(1).lower():
        rm = re.search(r"(\d\.\d+)\s*out of 5", m.group(1))
        if rm:
            rating = float(rm.group(1))

    return name, price, availability, rating


SCRAPE_PARSERS = {"target": parse_target_markdown, "newegg": parse_newegg_markdown}


def fetch_scraped(retailer, url, out_path, retries=2):
    for attempt in range(retries + 1):
        r = run(f'bdata scrape "{url}" --format markdown --zone web_unlocker -o "{out_path}"')
        if os.path.exists(out_path):
            text = open(out_path).read()
            if text.strip() and "Error:" not in text[:200]:
                return text, None
            err = text[:300]
        else:
            err = (r.stderr or r.stdout or "no output").strip()[-300:]
        if attempt < retries:
            time.sleep(3)
    return None, err


# ---------------------------- main data collection ----------------------------

def collect_results(skus):
    results = []
    for s in skus:
        sku_id, product = s["sku_id"], s["product"]
        for retailer, info in s["retailers"].items():
            url = info["url"]
            key = f"{sku_id}_{retailer}"
            entry = {"sku_id": sku_id, "product": product, "retailer": retailer, "url": url,
                      "name": None, "price": None, "availability": None, "rating": None, "status": None}
            print(f"  fetching {key} ...", file=sys.stderr)

            if retailer in SCRAPE_RETAILERS:
                out_path = os.path.join(RAW, f"{key}.md")
                text, err = fetch_scraped(retailer, url, out_path)
                if text is None:
                    entry["status"] = f"fetch error: {err}"
                else:
                    name, price, availability, rating = SCRAPE_PARSERS[retailer](text)
                    entry.update(name=name, price=price, availability=availability, rating=rating, status="ok")
            else:
                out_path = os.path.join(RAW, f"{key}.json")
                rec, err = fetch_structured(retailer, url, out_path)
                if rec is None:
                    entry["status"] = f"fetch error: {err}"
                else:
                    name, price, availability, rating = STRUCT_PARSERS[retailer](rec)
                    entry.update(name=name, price=price, availability=availability, rating=rating, status="ok")

            results.append(entry)
    return results


def collect_new_listings(skus):
    listings = []
    for s in skus:
        sku_id, product = s["sku_id"], s["product"]
        out_path = os.path.join(SEARCH, f"{sku_id}_web.json")
        r = run(f'bdata search "{product} buy" --country us --json -o "{out_path}"', timeout=120)
        urls = []
        try:
            data = json.load(open(out_path))
            for item in data.get("organic", []):
                link = item.get("link")
                if not link:
                    continue
                if any(b in link for b in BLOCKLIST_SUBSTRINGS):
                    continue
                if any(k in link for k in KNOWN_DOMAINS):
                    continue
                if link not in urls:
                    urls.append(link)
                if len(urls) >= 5:
                    break
        except Exception as e:
            print(f"  new_listings search failed for {sku_id}: {e}", file=sys.stderr)
        listings.append({"sku_id": sku_id, "product": product, "new_urls": urls})
    return listings


def main():
    skus = json.load(open(os.path.join(BASE, "skus.json")))

    print("Collecting price/availability/rating for all product pages...", file=sys.stderr)
    results = collect_results(skus)
    with open(os.path.join(BASE, "results.json"), "w") as f:
        json.dump(results, f, indent=2)

    print("Searching for new competitor listings...", file=sys.stderr)
    listings = collect_new_listings(skus)
    with open(os.path.join(BASE, "new_listings.json"), "w") as f:
        json.dump(listings, f, indent=2)

    total = len(results)
    ok = sum(1 for r in results if r["status"] == "ok")
    complete = sum(1 for r in results if all(r[k] is not None for k in ("name", "price", "availability", "rating")))
    print(f"\nDone. {ok}/{total} pages fetched successfully; {complete}/{total} pages have all four fields.")
    print("Open dashboard.html (served over http://, not file://) to view the price table.")


if __name__ == "__main__":
    main()
