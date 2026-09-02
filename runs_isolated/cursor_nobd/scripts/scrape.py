#!/usr/bin/env python3
"""Competitor price tracker.

Reads skus.json (read-only, never modified), visits every retailer product
page listed there, and writes results.json with the current product name,
price, availability and customer rating for each page.

Usage:
    python3 scripts/scrape.py

See README.md for the full one-command invocation.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch
import parsers

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKUS_PATH = os.path.join(ROOT, "skus.json")
RESULTS_PATH = os.path.join(ROOT, "results.json")

# Retailers whose price/availability is injected client-side and therefore
# require a real (headless) browser render rather than a plain HTTP fetch.
ALWAYS_RENDER = {"target"}

FIELDS_REQUIRED = ("name", "price", "availability", "rating")


def is_complete(parsed):
    return all(parsed.get(f) is not None for f in FIELDS_REQUIRED)


def merge(primary, secondary):
    """Fill in any missing fields of `primary` from `secondary`."""
    if secondary is None:
        return primary
    merged = dict(primary)
    for f in FIELDS_REQUIRED:
        if merged.get(f) is None and secondary.get(f) is not None:
            merged[f] = secondary[f]
    if is_complete(merged):
        merged["reason"] = None
    elif merged.get("reason") is None:
        merged["reason"] = secondary.get("reason")
    return merged


def rating_to_display(rating):
    if not rating:
        return None
    value = rating.get("value")
    count = rating.get("count")
    if value is None:
        return None
    if count is not None:
        return f"{value} ({count} reviews)"
    return f"{value}"


def scrape_one(sku_id, product, retailer, url, browser, verbose=True):
    log = lambda msg: print(f"  [{sku_id}/{retailer}] {msg}", file=sys.stderr) if verbose else None

    html, status_code, err = fetch.fetch_static(url, retailer)
    if html is not None:
        parsed = parsers.parse(retailer, html, url)
    else:
        parsed = parsers.empty_result(f"fetch_error: {err}")

    needs_render = retailer in ALWAYS_RENDER or not is_complete(parsed)
    if needs_render:
        log(f"static incomplete ({parsed.get('reason')}); trying headless-browser render")
        rendered_html, rerr = browser.fetch(
            url, retailer, wait_selector=fetch.WAIT_SELECTORS.get(retailer)
        )
        if rendered_html is not None:
            rendered_parsed = parsers.parse(retailer, rendered_html, url)
            parsed = merge(parsed, rendered_parsed) if html is not None else rendered_parsed
        elif html is None:
            parsed = parsers.empty_result(f"fetch_error: {rerr}")

    status = "ok" if is_complete(parsed) else (parsed.get("reason") or "unknown_error")

    return {
        "sku_id": sku_id,
        "product": product,
        "retailer": retailer,
        "url": url,
        "name": parsed.get("name"),
        "price": parsed.get("price"),
        "availability": parsed.get("availability"),
        "rating": rating_to_display(parsed.get("rating")),
        "status": status,
    }


def main():
    with open(SKUS_PATH) as f:
        skus = json.load(f)

    targets = []
    for sku in skus:
        for retailer, info in sku["retailers"].items():
            targets.append((sku["sku_id"], sku["product"], retailer, info["url"]))

    print(f"Fetching {len(targets)} product pages across {len(skus)} products...", file=sys.stderr)

    browser = fetch.BrowserFetcher()
    results = []
    ok_count = 0
    try:
        for i, (sku_id, product, retailer, url) in enumerate(targets, 1):
            print(f"[{i}/{len(targets)}] {sku_id} {retailer} -> {url}", file=sys.stderr)
            t0 = time.time()
            row = scrape_one(sku_id, product, retailer, url, browser)
            dt = time.time() - t0
            print(f"    status={row['status']!r} ({dt:.1f}s)", file=sys.stderr)
            if row["status"] == "ok":
                ok_count += 1
            results.append(row)
    finally:
        browser.stop()

    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nWrote {len(results)} rows to {RESULTS_PATH}", file=sys.stderr)
    print(f"Fully collected (all 4 fields): {ok_count}/{len(targets)}", file=sys.stderr)


if __name__ == "__main__":
    main()
