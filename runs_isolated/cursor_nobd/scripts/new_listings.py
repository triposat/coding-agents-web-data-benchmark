#!/usr/bin/env python3
"""Discover additional retailer listings for each SKU via public web search.

For each of the 10 products in skus.json, this runs a public DuckDuckGo HTML
search (no API key / no login) and records up to 5 additional retailer
product-page URLs that are not already listed in skus.json.

Usage:
    python3 scripts/new_listings.py
"""
import json
import os
import re
import sys
import time
from urllib.parse import unquote, urlparse

from curl_cffi import requests as cffi_requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKUS_PATH = os.path.join(ROOT, "skus.json")
OUT_PATH = os.path.join(ROOT, "new_listings.json")

MAX_PER_PRODUCT = 5

# Domains that are not retailers (news/review/social/forum/marketplace-search
# aggregators, manufacturer support pages, etc.) and should not be counted as
# "retailer URLs selling the same product".
NON_RETAILER_DOMAINS = {
    "en.wikipedia.org", "wikipedia.org", "youtube.com", "www.youtube.com",
    "reddit.com", "www.reddit.com", "quora.com", "www.quora.com",
    "facebook.com", "www.facebook.com", "instagram.com", "www.instagram.com",
    "pinterest.com", "www.pinterest.com", "twitter.com", "x.com",
    "cnet.com", "www.cnet.com", "theverge.com", "www.theverge.com",
    "engadget.com", "www.engadget.com", "rtings.com", "www.rtings.com",
    "pcmag.com", "www.pcmag.com", "wired.com", "www.wired.com",
    "consumerreports.org", "www.consumerreports.org", "tomsguide.com", "www.tomsguide.com",
    "wikipedia.com", "reviewed.com", "www.reviewed.com", "gizmodo.com", "www.gizmodo.com",
    "pricehistory.app", "gadgets360.com", "lifehacker.com", "ign.com",
    "klarna.com", "camelcamelcamel.com", "slickdeals.net", "www.slickdeals.net",
    "androidcentral.com", "digitaltrends.com", "techradar.com", "www.techradar.com",
    "businessinsider.com", "nytimes.com", "forbes.com", "gsmarena.com",
    "hip2save.com", "zdnet.com", "www.zdnet.com", "dealnews.com",
    "thekrazycouponlady.com", "offers.com", "retailmenot.com",
    "upgradedpoints.com", "aivanet.com", "selects.gg", "9to5toys.com",
    "kinja-static.com",
}

# URL substrings that indicate a generic search/listing page rather than a
# specific product page (not useful as a "retailer URL selling the product").
SEARCH_PAGE_MARKERS = ("_nkw=", "/sch/", "/s?k=", "/search?", "/collection/", "/collections/")


def _strip_www(netloc):
    return netloc[4:] if netloc.startswith("www.") else netloc


def load_existing_domains(sku):
    domains = set()
    for info in sku["retailers"].values():
        domains.add(_strip_www(urlparse(info["url"]).netloc.lower()))
    return domains


def search(query, n=30, retries=2):
    for attempt in range(retries + 1):
        try:
            r = cffi_requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                impersonate="chrome",
                timeout=20,
            )
            raw_links = re.findall(r'class="result__a"[^>]*href="([^"]+)"', r.text)
            out = []
            for link in raw_links[:n]:
                m = re.search(r"uddg=([^&]+)", link)
                url = unquote(m.group(1)) if m else link
                if url.startswith("http"):
                    out.append(url)
            return out
        except Exception:
            time.sleep(2)
    return []


def normalize_domain(url):
    return _strip_www(urlparse(url).netloc.lower())


def main():
    with open(SKUS_PATH) as f:
        skus = json.load(f)

    listings = []
    for sku in skus:
        product = sku["product"]
        existing_domains = load_existing_domains(sku)
        print(f"Searching for additional retailers: {product}", file=sys.stderr)

        results = search(f"{product} buy price")
        seen_domains = set(existing_domains)
        found = []
        deferred = []  # search-listing-page URLs, used only if nothing better exists
        for url in results:
            domain = normalize_domain(url)
            if not domain or domain in seen_domains or domain in NON_RETAILER_DOMAINS:
                continue
            if domain.endswith(".gov") or domain.endswith(".edu"):
                continue
            if any(marker in url for marker in SEARCH_PAGE_MARKERS):
                if domain not in {normalize_domain(u) for u in deferred}:
                    deferred.append(url)
                continue
            seen_domains.add(domain)
            found.append(url)
            if len(found) >= MAX_PER_PRODUCT:
                break

        for url in deferred:
            if len(found) >= MAX_PER_PRODUCT:
                break
            domain = normalize_domain(url)
            if domain in seen_domains:
                continue
            seen_domains.add(domain)
            found.append(url)

        print(f"  -> found {len(found)} new retailer URLs", file=sys.stderr)
        listings.append(
            {
                "sku_id": sku["sku_id"],
                "product": product,
                "new_retailer_urls": found,
            }
        )
        time.sleep(1)

    with open(OUT_PATH, "w") as f:
        json.dump(listings, f, indent=2)
    print(f"\nWrote {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
