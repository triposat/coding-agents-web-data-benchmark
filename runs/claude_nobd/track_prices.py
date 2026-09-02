#!/usr/bin/env python3
"""
Competitor price tracker.

Reads skus.json (never modified), fetches product data for every retailer
page via the `bdata` CLI (Bright Data), and writes:
  - results.json       one row per (sku, retailer) page with the 4 tracked fields
  - new_listings.json  up to 5 additional retailer URLs per product, found via web search

Usage:
  uv run track_prices.py
  (or: python3 track_prices.py)
"""

import json
import re
import subprocess
import sys
import tempfile
import os
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
SKUS_PATH = HERE / "skus.json"
RESULTS_PATH = HERE / "results.json"
NEW_LISTINGS_PATH = HERE / "new_listings.json"

PIPELINE_BY_RETAILER = {
    "amazon": "amazon_product",
    "bestbuy": "bestbuy_products",
    "walmart": "walmart_product",
}

PIPELINE_TIMEOUT = 480  # seconds; bestbuy_products has been observed to take several minutes
SCRAPE_TIMEOUT = 120


def run_bdata(args, timeout):
    try:
        proc = subprocess.run(
            ["bdata", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return None, "", "timeout"
    except FileNotFoundError:
        return None, "", "bdata CLI not found on PATH"


def to_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^0-9.]", "", value)
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None
    return None


def normalize_availability(*candidates):
    for c in candidates:
        if c is None:
            continue
        if isinstance(c, bool):
            return "In Stock" if c else "Out of Stock"
        if isinstance(c, str) and c.strip():
            return c.strip().replace("_", " ").title()
    return None


def fetch_via_pipeline(pipeline, url):
    """Run a bdata structured pipeline for amazon/bestbuy/walmart, return parsed dict + status."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        rc, out, err = run_bdata(["pipelines", pipeline, url, "-o", tmp_path], PIPELINE_TIMEOUT)
        if rc is None:
            return {}, f"pipeline_error: {err or 'timeout'}"
        if rc != 0:
            return {}, f"pipeline_error: {(err or out).strip()[:200]}"
        try:
            data = json.loads(Path(tmp_path).read_text())
        except (json.JSONDecodeError, OSError) as e:
            return {}, f"pipeline_error: could not parse output ({e})"
        if not data or not isinstance(data, list):
            return {}, "pipeline_error: empty result"
        row = data[0]
        if row.get("error"):
            return {}, f"pipeline_error: {row.get('error')}"
        return row, None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def extract_amazon(row):
    name = row.get("title") or row.get("title_clean")
    price = to_number(row.get("final_price") if row.get("final_price") is not None else row.get("initial_price"))
    availability = normalize_availability(row.get("availability"), row.get("is_available"))
    rating = to_number(row.get("rating"))
    return name, price, availability, rating


def extract_bestbuy(row):
    name = row.get("title")
    price = to_number(row.get("final_price") if row.get("final_price") is not None else row.get("price"))
    availability = normalize_availability(row.get("availability_new"))
    rating = to_number(row.get("rating"))
    return name, price, availability, rating


def extract_walmart(row):
    name = row.get("product_name")
    price = to_number(row.get("final_price") if row.get("final_price") is not None else row.get("price"))
    availability = normalize_availability(row.get("availability_text"), row.get("is_available"), row.get("availability"))
    rating = to_number(row.get("rating"))
    return name, price, availability, rating


EXTRACTORS = {
    "amazon": extract_amazon,
    "bestbuy": extract_bestbuy,
    "walmart": extract_walmart,
}


def fetch_via_scrape(url):
    """Fallback for retailers with no dedicated pipeline (e.g. target, newegg):
    use bdata's Web Unlocker (markdown) and parse heuristically."""
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        rc, out, err = run_bdata(["scrape", url, "--format", "markdown", "-o", tmp_path], SCRAPE_TIMEOUT)
        if rc is None:
            return None, None, None, None, f"scrape_error: {err or 'timeout'}"
        if rc != 0:
            return None, None, None, None, f"scrape_error: {(err or out).strip()[:200]}"
        try:
            text = Path(tmp_path).read_text(errors="ignore")
        except OSError as e:
            return None, None, None, None, f"scrape_error: could not read output ({e})"
        if not text.strip():
            return None, None, None, None, "scrape_error: empty page"

        name = None
        h1 = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if h1:
            name = h1.group(1).strip()
        else:
            title = re.search(r"<title>([^<]+)</title>", text)
            if title:
                name = title.group(1).strip()

        prices = [to_number(p) for p in re.findall(r"\$\s?[\d,]+\.\d{2}", text)]
        prices = [p for p in prices if p]
        price = prices[0] if prices else None

        rating = None
        m = re.search(r"([0-5](?:\.\d)?)\s*(?:out of|/)\s*5", text, re.IGNORECASE)
        if m:
            rating = to_number(m.group(1))

        availability = None
        m = re.search(r"\b(in stock|out of stock|sold out|limited stock|available)\b", text, re.IGNORECASE)
        if m:
            availability = m.group(1).title()

        return name, price, availability, rating, None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def collect_results(skus):
    results = []
    for product in skus:
        sku_id = product["sku_id"]
        name_ = product["product"]
        for retailer, info in product["retailers"].items():
            url = info["url"]
            row = {
                "sku_id": sku_id,
                "product": name_,
                "retailer": retailer,
                "url": url,
                "name": None,
                "price": None,
                "availability": None,
                "rating": None,
                "status": None,
            }
            pipeline = PIPELINE_BY_RETAILER.get(retailer)
            if pipeline:
                raw, err = fetch_via_pipeline(pipeline, url)
                if err and not raw:
                    row["status"] = err
                else:
                    name, price, availability, rating = EXTRACTORS[retailer](raw)
                    row["name"], row["price"], row["availability"], row["rating"] = name, price, availability, rating
                    missing = [k for k in ("name", "price", "availability", "rating") if row[k] is None]
                    row["status"] = "ok" if not missing else f"missing_fields: {','.join(missing)}"
            else:
                name, price, availability, rating, err = fetch_via_scrape(url)
                row["name"], row["price"], row["availability"], row["rating"] = name, price, availability, rating
                if err:
                    row["status"] = err
                else:
                    missing = [k for k in ("name", "price", "availability", "rating") if row[k] is None]
                    row["status"] = "ok" if not missing else f"missing_fields: {','.join(missing)}"
            print(f"[{sku_id}/{retailer}] status={row['status']}", file=sys.stderr)
            results.append(row)
    return results


def collect_new_listings(skus):
    listings = []
    for product in skus:
        sku_id = product["sku_id"]
        name_ = product["product"]
        existing_domains = {urlparse(r["url"]).netloc.replace("www.", "") for r in product["retailers"].values()}
        found = []
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            rc, out, err = run_bdata(
                ["search", f"{name_} buy", "--type", "shopping", "-o", tmp_path],
                90,
            )
            if rc == 0:
                try:
                    data = json.loads(Path(tmp_path).read_text())
                    items = data if isinstance(data, list) else data.get("shopping_results", data.get("organic", []))
                    for item in items:
                        url = item.get("link") or item.get("url")
                        if not url:
                            continue
                        domain = urlparse(url).netloc.replace("www.", "")
                        if domain in existing_domains or any(f["url"] == url for f in found):
                            continue
                        existing_domains.add(domain)
                        found.append({"retailer": domain, "url": url})
                        if len(found) >= 5:
                            break
                except (json.JSONDecodeError, OSError):
                    pass
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        print(f"[{sku_id}] new listings found: {len(found)}", file=sys.stderr)
        listings.append({"sku_id": sku_id, "product": name_, "new_listings": found})
    return listings


def main():
    skus = json.loads(SKUS_PATH.read_text())

    results = collect_results(skus)
    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    ok_count = sum(1 for r in results if r["status"] == "ok")
    print(f"Wrote {RESULTS_PATH.name}: {ok_count}/{len(results)} pages fully collected", file=sys.stderr)

    new_listings = collect_new_listings(skus)
    NEW_LISTINGS_PATH.write_text(json.dumps(new_listings, indent=2))
    print(f"Wrote {NEW_LISTINGS_PATH.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
