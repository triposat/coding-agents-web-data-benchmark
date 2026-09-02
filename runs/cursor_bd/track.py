#!/usr/bin/env python3
"""Competitor price tracker: scrape product pages and discover new listings."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from brightdata import BrightDataClient, strip_security_markers
from parsers import build_status, detect_retailer, parse_product

ROOT = Path(__file__).resolve().parent
SKUS_PATH = ROOT / "skus.json"
RESULTS_PATH = ROOT / "results.json"
NEW_LISTINGS_PATH = ROOT / "new_listings.json"
CACHE_PATH = ROOT / ".cache" / "scrapes.json"

RETAILER_DOMAINS = {
    "amazon.com": "amazon",
    "www.amazon.com": "amazon",
    "bestbuy.com": "bestbuy",
    "www.bestbuy.com": "bestbuy",
    "walmart.com": "walmart",
    "www.walmart.com": "walmart",
    "target.com": "target",
    "www.target.com": "target",
    "newegg.com": "newegg",
    "www.newegg.com": "newegg",
    "bhphotovideo.com": "bhphoto",
    "www.bhphotovideo.com": "bhphoto",
    "adorama.com": "adorama",
    "www.adorama.com": "adorama",
    "costco.com": "costco",
    "www.costco.com": "costco",
    "ebay.com": "ebay",
    "www.ebay.com": "ebay",
    "apple.com": "apple",
    "www.apple.com": "apple",
    "anker.com": "anker",
    "www.anker.com": "anker",
    "bose.com": "bose",
    "www.bose.com": "bose",
    "cdw.com": "cdw",
    "www.cdw.com": "cdw",
    "staples.com": "staples",
    "www.staples.com": "staples",
    "officedepot.com": "officedepot",
    "www.officedepot.com": "officedepot",
    "samsung.com": "samsung",
    "www.samsung.com": "samsung",
    "logitech.com": "logitech",
    "www.logitech.com": "logitech",
    "razer.com": "razer",
    "www.razer.com": "razer",
    "seagate.com": "seagate",
    "www.seagate.com": "seagate",
    "sandisk.com": "sandisk",
    "www.sandisk.com": "sandisk",
    "sony.com": "sony",
    "www.sony.com": "sony",
}

SKIP_DOMAINS = {
    "reddit.com",
    "www.reddit.com",
    "youtube.com",
    "www.youtube.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "wikipedia.org",
    "support.",
    "kb.",
    "help.",
    "camelcamelcamel.com",
    "promotions.",
    "service.",
}


def load_skus() -> list[dict]:
    return json.loads(SKUS_PATH.read_text())


def flatten_targets(skus: list[dict]) -> list[dict]:
    targets = []
    for sku in skus:
        for retailer, info in sku["retailers"].items():
            targets.append(
                {
                    "sku_id": sku["sku_id"],
                    "product": sku["product"],
                    "retailer": retailer,
                    "url": info["url"],
                }
            )
    return targets


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}"


def existing_url_set(skus: list[dict]) -> set[str]:
    urls = set()
    for sku in skus:
        for info in sku["retailers"].values():
            urls.add(normalize_url(info["url"]))
    return urls


def is_product_url(url: str) -> bool:
    lower = url.lower()
    if any(skip in lower for skip in SKIP_DOMAINS):
        return False
    host = urlparse(url).netloc.lower()
    if host not in RETAILER_DOMAINS:
        # Allow other retailer-looking product paths
        product_hints = ("/dp/", "/ip/", "/p/", "/product/", "/sku/", "/N82E168", "/pdp/")
        return any(h in lower for h in product_hints)
    return True


def retailer_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host in RETAILER_DOMAINS:
        return RETAILER_DOMAINS[host]
    parts = host.split(".")
    if len(parts) >= 2:
        return parts[-2]
    return host


def scrape_all(client: BrightDataClient, targets: list[dict], *, refresh: bool = False) -> list[dict]:
    results: list[dict] = []
    scraped: dict[str, str] = {}

    if not refresh and CACHE_PATH.exists():
        scraped = json.loads(CACHE_PATH.read_text())
        print(f"Loaded {len(scraped)} cached page(s)", flush=True)

    pending = [
        t
        for t in targets
        if refresh or not scraped.get(t["url"]) or len(scraped.get(t["url"], "")) < 100
    ]

    while pending:
        batch = pending[:10]
        pending = pending[10:]
        urls = [t["url"] for t in batch]
        print(f"Scraping batch of {len(urls)}...", flush=True)
        try:
            batch_content = client.scrape_batch(urls)
        except Exception as exc:
            print(f"  batch error: {exc}", flush=True)
            batch_content = {}

        for target in batch:
            url = target["url"]
            content = batch_content.get(url, "")
            if not content or len(content) < 100:
                for attempt in range(3):
                    try:
                        if attempt > 0:
                            client.reconnect()
                            time.sleep(2 * attempt)
                        print(f"  retry single ({attempt + 1}): {target['retailer']}", flush=True)
                        content = strip_security_markers(client.scrape(url))
                        if content and len(content) >= 100:
                            break
                    except Exception as exc:
                        print(f"  scrape failed {url}: {exc}", flush=True)
                        content = ""
            scraped[url] = content

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(scraped, indent=2))

    for target in targets:
        url = target["url"]
        content = scraped.get(url, "")
        scrape_ok = bool(content and len(content) >= 100)
        fields = parse_product(url, content) if scrape_ok else {
            "name": None,
            "price": None,
            "availability": None,
            "rating": None,
        }
        status = build_status(fields, scrape_ok=scrape_ok)
        results.append(
            {
                "sku_id": target["sku_id"],
                "product": target["product"],
                "retailer": target["retailer"],
                "url": url,
                "name": fields["name"],
                "price": fields["price"],
                "availability": fields["availability"],
                "rating": fields["rating"],
                "status": status,
            }
        )
        print(
            f"  {target['sku_id']} / {target['retailer']}: {status}"
            + (f" @ {fields['price']}" if fields.get("price") else ""),
            flush=True,
        )

    return results


def discover_new_listings(client: BrightDataClient, skus: list[dict]) -> list[dict]:
    known = existing_url_set(skus)
    known_retailers_by_sku = {
        sku["sku_id"]: set(sku["retailers"].keys()) for sku in skus
    }
    listings = []

    queries = [f"{sku['product']} buy price" for sku in skus]
    print("Searching for new retailer listings...", flush=True)

    for i in range(0, len(queries), 10):
        chunk = queries[i : i + 10]
        chunk_skus = skus[i : i + 10]
        try:
            search_results = client.search_batch(chunk)
        except Exception as exc:
            print(f"  batch search error: {exc}", flush=True)
            client.reconnect()
            search_results = {}
            for q in chunk:
                try:
                    search_results[q] = client.search(q)
                    time.sleep(1)
                except Exception:
                    search_results[q] = []

        for sku, query in zip(chunk_skus, chunk):
            organic = search_results.get(query, [])
            if not organic:
                try:
                    organic = client.search(query)
                except Exception:
                    organic = []

            found = []
            seen_urls: set[str] = set()
            for item in organic:
                link = item.get("link", "")
                if not link or not is_product_url(link):
                    continue
                norm = normalize_url(link)
                if norm in known or norm in seen_urls:
                    continue
                retailer = retailer_from_url(link)
                if retailer in known_retailers_by_sku[sku["sku_id"]]:
                    continue
                seen_urls.add(norm)
                found.append(
                    {
                        "retailer": retailer,
                        "url": link,
                        "title": item.get("title", ""),
                    }
                )
                if len(found) >= 5:
                    break

            listings.append(
                {
                    "sku_id": sku["sku_id"],
                    "product": sku["product"],
                    "new_listings": found,
                }
            )
            print(
                f"  {sku['sku_id']}: {len(found)} new listing(s)",
                flush=True,
            )
        time.sleep(1)

    return listings


def count_full_success(results: list[dict]) -> int:
    return sum(1 for r in results if r["status"] == "ok")


def main() -> int:
    refresh = "--refresh" in sys.argv
    skus = load_skus()
    targets = flatten_targets(skus)
    print(f"Tracking {len(targets)} product pages across {len(skus)} SKUs", flush=True)

    client = BrightDataClient()
    client.connect()

    results = scrape_all(client, targets, refresh=refresh)
    RESULTS_PATH.write_text(json.dumps(results, indent=2) + "\n")
    print(f"Wrote {RESULTS_PATH}", flush=True)

    new_listings = discover_new_listings(client, skus)
    NEW_LISTINGS_PATH.write_text(json.dumps(new_listings, indent=2) + "\n")
    print(f"Wrote {NEW_LISTINGS_PATH}", flush=True)

    ok_count = count_full_success(results)
    print(f"\nCollected all 4 fields for {ok_count} of {len(results)} pages.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
