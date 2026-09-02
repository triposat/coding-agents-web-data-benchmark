#!/usr/bin/env python3
"""Competitor price tracker: scrape retailer pages and discover new listings."""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import BrowserContext, Page, sync_playwright

ROOT = Path(__file__).resolve().parent
SKUS_PATH = ROOT / "skus.json"
RESULTS_PATH = ROOT / "results.json"
NEW_LISTINGS_PATH = ROOT / "new_listings.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)

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
    "staples.com": "staples",
    "www.staples.com": "staples",
    "microcenter.com": "microcenter",
    "www.microcenter.com": "microcenter",
    "apple.com": "apple",
    "www.apple.com": "apple",
    "samsung.com": "samsung",
    "www.samsung.com": "samsung",
}


@dataclass
class ScrapeResult:
    name: str | None
    price: str | None
    availability: str | None
    rating: str | None
    status: str

    def complete(self) -> bool:
        return all(
            v is not None and str(v).strip() != ""
            for v in (self.name, self.price, self.availability, self.rating)
        )


def load_skus() -> list[dict[str, Any]]:
    with SKUS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def normalize_price(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", text.strip())
    match = re.search(r"(\$|USD\s*)[\d,]+\.?\d*", text)
    if match:
        return match.group(0).strip()
    match = re.search(r"[\d,]+\.?\d*", text)
    if match and match.group(0) not in ("", "."):
        return f"${match.group(0)}"
    return None


def parse_rating(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"([\d.]+)\s*(?:out of|/)\s*5", text, re.I)
    if match:
        return match.group(1)
    match = re.search(r"([\d.]+)\s*out of\s*5\s*eggs", text, re.I)
    if match:
        return match.group(1)
    match = re.search(r"^([\d.]+)$", text.strip())
    return match.group(1) if match else text.strip()[:20] or None


def parse_json_ld(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "Product":
                offers = item.get("offers", {})
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                agg = item.get("aggregateRating", {}) or {}
                availability = offers.get("availability", "")
                if isinstance(availability, str) and availability.startswith("http"):
                    availability = availability.rsplit("/", 1)[-1]
                return {
                    "name": item.get("name"),
                    "price": offers.get("price") or offers.get("lowPrice"),
                    "availability": availability or offers.get("availability"),
                    "rating": agg.get("ratingValue"),
                }
    return {}


def ensure_amazon_us_zip(page: Page) -> None:
    page.goto("https://www.amazon.com/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1000)
    page.evaluate(
        """async () => {
        const form = new URLSearchParams();
        form.append('locationType', 'LOCATION_INPUT');
        form.append('zipCode', '10001');
        form.append('storeContext', 'generic');
        form.append('deviceType', 'web');
        form.append('pageType', 'Gateway');
        form.append('actionSource', 'glow');
        await fetch('https://www.amazon.com/gp/delivery/ajax/address-change.html', {
            method: 'POST',
            credentials: 'include',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: form.toString()
        });
    }"""
    )


def inpage_fetch(page: Page, url: str) -> str:
    return page.evaluate(
        """async (url) => {
        const response = await fetch(url, {credentials: 'include'});
        return await response.text();
    }""",
        url,
    )


def scrape_amazon(page: Page, url: str, warmed: bool) -> ScrapeResult:
    last_error: ScrapeResult | None = None
    for attempt in range(2):
        try:
            if attempt == 0:
                ensure_amazon_us_zip(page)
            elif not warmed:
                ensure_amazon_us_zip(page)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            if page.locator("input#captchacharacters").count() or page.title().strip() == "Amazon.com":
                if attempt == 0:
                    continue
                return ScrapeResult(None, None, None, None, "bot challenge")

            name = None
            if page.locator("span#productTitle").count():
                name = page.locator("span#productTitle").first.inner_text().strip()

            price = None
            for selector in (
                "#buybox .a-offscreen",
                "#corePriceDisplay_desktop_feature_div .a-offscreen",
                "#apex_desktop .a-offscreen",
                ".priceToPay .a-offscreen",
                "#corePrice_feature_div .a-offscreen",
            ):
                loc = page.locator(selector)
                if loc.count():
                    candidate = normalize_price(loc.first.inner_text().strip())
                    if candidate:
                        price = candidate
                        break

            availability = None
            if page.locator("#availability").count():
                availability = page.locator("#availability").first.inner_text().strip()
            if not availability and page.locator("#outOfStock").count():
                availability = page.locator("#outOfStock").first.inner_text().strip()

            rating = None
            if page.locator("#acrPopover").count():
                rating = parse_rating(page.locator("#acrPopover").first.get_attribute("title"))
            if not rating and page.locator("span[data-hook='rating-out-of-text']").count():
                rating = parse_rating(
                    page.locator("span[data-hook='rating-out-of-text']").first.inner_text()
                )

            if not price:
                html = page.content()
                for pattern in (
                    r'priceToPay.*?a-offscreen">\$?([^<]+)',
                    r'"priceAmount":\s*([\d.]+)',
                    r'"currencyCode":"USD"[^}]*"priceAmount":\s*([\d.]+)',
                ):
                    match = re.search(pattern, html, re.DOTALL)
                    if match:
                        price = normalize_price(f"${match.group(1)}")
                        if price:
                            break
                if not price:
                    for selector in (".basisPrice .a-offscreen", "#listPrice"):
                        loc = page.locator(selector)
                        if loc.count():
                            price = normalize_price(loc.first.inner_text().strip())
                            if price:
                                break

            price = normalize_price(price)
            if availability is not None and availability.strip() == "":
                availability = None

            if not all([name, price, availability, rating]):
                missing = [
                    field
                    for field, val in (
                        ("name", name),
                        ("price", price),
                        ("availability", availability),
                        ("rating", rating),
                    )
                    if not val
                ]
                last_error = ScrapeResult(
                    name, price, availability, rating, f"missing: {', '.join(missing)}"
                )
                if attempt == 0 and not name:
                    continue
                return last_error
            return ScrapeResult(name, price, availability, rating, "ok")
        except Exception as exc:
            last_error = ScrapeResult(None, None, None, None, str(exc)[:120])
            if attempt == 0:
                continue
    return last_error or ScrapeResult(None, None, None, None, "scrape failed")


def scrape_target(page: Page, url: str) -> ScrapeResult:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector('[data-test="product-title"]', timeout=20000)
        page.wait_for_timeout(2500)

        name = page.locator('h1[data-test="product-title"]').first.inner_text().strip()
        body = page.inner_text("body")

        price = None
        try:
            page.wait_for_selector('[data-test="product-price"]', state="attached", timeout=15000)
            for candidate in page.locator('[data-test="product-price"]').all():
                value = candidate.inner_text().strip()
                if value:
                    price = value
                    break
        except Exception:
            pass
        if not price:
            match = re.search(r"\$[\d,.]+", body)
            price = match.group(0) if match else None
        price = normalize_price(price)

        rating = None
        if page.locator('[data-test="ratings"]').count():
            rating = parse_rating(page.locator('[data-test="ratings"]').first.inner_text())
        if not rating:
            rating = parse_rating(re.search(r"([\d.]+)\s*out of 5 stars", body, re.I).group(0) if re.search(r"([\d.]+)\s*out of 5 stars", body, re.I) else None)

        availability_parts: list[str] = []
        if page.locator('[data-test="fulfillment-cell"]').count():
            for cell in page.locator('[data-test="fulfillment-cell"]').all()[:3]:
                availability_parts.append(re.sub(r"\s+", " ", cell.inner_text().strip()))
        availability = "; ".join(part for part in availability_parts if part) or None
        if not availability:
            if re.search(r"out of stock", body, re.I):
                availability = "Out of stock"
            elif re.search(r"pickup\s+not available", body, re.I):
                availability = "Pickup not available"
            elif re.search(r"in stock", body, re.I):
                availability = "In stock"
            elif re.search(r"delivery", body, re.I):
                availability = "Check delivery availability"

        if not all([name, price, availability, rating]):
            missing = [
                field
                for field, val in (
                    ("name", name),
                    ("price", price),
                    ("availability", availability),
                    ("rating", rating),
                )
                if not val
            ]
            return ScrapeResult(name, price, availability, rating, f"missing: {', '.join(missing)}")
        return ScrapeResult(name, price, availability, rating, "ok")
    except Exception as exc:
        return ScrapeResult(None, None, None, None, str(exc)[:120])


def scrape_newegg(page: Page, url: str, warmed: bool) -> ScrapeResult:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        if "Are you a human" in page.title() or "CAPTCHA" in page.title():
            page.goto("https://www.newegg.com/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)
            html = inpage_fetch(page, url)
            if "Are you a human" in html or "CAPTCHA" in html:
                return ScrapeResult(None, None, None, None, "bot challenge")
        else:
            html = page.content()

        soup = BeautifulSoup(html, "lxml")
        ld = parse_json_ld(html)

        name = ld.get("name")
        title = soup.select_one(".product-title") or soup.select_one("h1")
        if title:
            name = name or title.get_text(strip=True)

        price = ld.get("price")
        price_el = soup.select_one(".product-price") or soup.select_one(".price-current")
        if price_el:
            price = price or normalize_price(price_el.get_text(" ", strip=True))

        rating = ld.get("rating")
        rating_el = soup.select_one(".product-rating .rating") or soup.select_one("i.rating")
        if rating_el:
            rating = rating or parse_rating(rating_el.get("title") or rating_el.get_text())
        if not rating:
            egg_match = re.search(r"([\d.]+)\s*out of\s*5\s*eggs", html, re.I)
            if egg_match:
                rating = egg_match.group(1)

        availability = ld.get("availability")
        if not availability:
            flag = soup.select_one(".product-flag") or soup.select_one(".product-inventory")
            if flag:
                availability = flag.get_text(" ", strip=True)
            elif soup.select_one(".btn-primary") or soup.select_one("#ProductBuy"):
                availability = "In stock"
            elif re.search(r"out of stock", html, re.I):
                availability = "Out of stock"
            elif price:
                availability = "Available"

        if isinstance(price, (int, float)):
            price = f"${price}"

        if not all([name, price, availability, rating]):
            missing = [
                field
                for field, val in (
                    ("name", name),
                    ("price", price),
                    ("availability", availability),
                    ("rating", rating),
                )
                if not val
            ]
            return ScrapeResult(name, price, availability, rating, f"missing: {', '.join(missing)}")
        return ScrapeResult(name, price, availability, rating, "ok")
    except Exception as exc:
        return ScrapeResult(None, None, None, None, str(exc)[:120])


def scrape_walmart(page: Page, url: str, warmed: bool) -> ScrapeResult:
    try:
        if not warmed:
            page.goto("https://www.walmart.com/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        if "Robot or human" in page.title():
            html = inpage_fetch(page, url)
            if "Robot or human" in html:
                return ScrapeResult(None, None, None, None, "bot challenge")
        else:
            html = page.content()

        ld = parse_json_ld(html)
        name = ld.get("name")
        price = ld.get("price")
        availability = ld.get("availability")
        rating = ld.get("rating")

        if "__NEXT_DATA__" in html:
            match = re.search(
                r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
            )
            if match:
                data = json.loads(match.group(1))
                blob = json.dumps(data)
                if not name:
                    name_match = re.search(r'"name":"([^"]{5,200})"', blob)
                    if name_match:
                        name = name_match.group(1)
                if not price:
                    price_match = re.search(
                        r'"currentPrice":\{"price":([\d.]+)[^}]*"priceString":"([^"]+)"',
                        blob,
                    )
                    if price_match:
                        price = price_match.group(2) or f"${price_match.group(1)}"
                if not rating:
                    rating_match = re.search(r'"averageRating":([\d.]+)', blob)
                    if rating_match:
                        rating = rating_match.group(1)
                if not availability:
                    avail_match = re.search(r'"availabilityStatus":"([^"]+)"', blob)
                    if avail_match:
                        availability = avail_match.group(1)

        soup = BeautifulSoup(html, "lxml")
        if not name:
            h1 = soup.select_one("h1")
            name = h1.get_text(strip=True) if h1 else None
        if not price:
            for selector in ('[itemprop="price"]', '[data-testid="price-wrap"]'):
                el = soup.select_one(selector)
                if el:
                    price = normalize_price(el.get("content") or el.get_text(strip=True))
                    break

        if isinstance(price, (int, float)):
            price = f"${price}"

        if not all([name, price, availability, rating]):
            missing = [
                field
                for field, val in (
                    ("name", name),
                    ("price", price),
                    ("availability", availability),
                    ("rating", rating),
                )
                if not val
            ]
            return ScrapeResult(name, price, availability, rating, f"missing: {', '.join(missing)}")
        return ScrapeResult(name, price, availability, rating, "ok")
    except Exception as exc:
        return ScrapeResult(None, None, None, None, str(exc)[:120])


def scrape_bestbuy(page: Page, url: str) -> ScrapeResult:
    try:
        site_url = url
        if "/product/" in url and "/sku/" in url:
            sku = url.rstrip("/").split("/")[-1]
            site_url = f"https://www.bestbuy.com/site/{sku}.p?intl=nosplash"
        page.goto(site_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        if "Choose a country" in page.title():
            return ScrapeResult(None, None, None, None, "geo redirect")

        html = page.content()
        ld = parse_json_ld(html)
        name = ld.get("name")
        price = ld.get("price")
        availability = ld.get("availability")
        rating = ld.get("rating")

        if page.locator("h1").count():
            name = name or page.locator("h1").first.inner_text().strip()
        if page.locator(".pricing-price__value").count():
            price = price or normalize_price(
                page.locator(".pricing-price__value").first.inner_text()
            )
        if page.locator('[data-testid="customer-rating"]').count():
            rating = rating or parse_rating(
                page.locator('[data-testid="customer-rating"]').first.inner_text()
            )
        if page.locator(".fulfillment-add-to-cart-button").count():
            availability = availability or "Available"
        elif page.locator(".c-button-disabled").count():
            availability = availability or "Unavailable"

        if isinstance(price, (int, float)):
            price = f"${price}"

        if not all([name, price, availability, rating]):
            missing = [
                field
                for field, val in (
                    ("name", name),
                    ("price", price),
                    ("availability", availability),
                    ("rating", rating),
                )
                if not val
            ]
            return ScrapeResult(name, price, availability, rating, f"missing: {', '.join(missing)}")
        return ScrapeResult(name, price, availability, rating, "ok")
    except Exception as exc:
        return ScrapeResult(None, None, None, None, str(exc)[:120])


def scrape_page(
    page: Page,
    retailer: str,
    url: str,
    warmed: dict[str, bool],
) -> ScrapeResult:
    retailer = retailer.lower()
    if retailer == "amazon":
        return scrape_amazon(page, url, warmed.get("amazon", False))
    if retailer == "target":
        return scrape_target(page, url)
    if retailer == "newegg":
        return scrape_newegg(page, url, warmed.get("newegg", False))
    if retailer == "walmart":
        return scrape_walmart(page, url, warmed.get("walmart", False))
    if retailer == "bestbuy":
        return scrape_bestbuy(page, url)
    return ScrapeResult(None, None, None, None, f"unsupported retailer: {retailer}")


def warm_context(context: BrowserContext) -> dict[str, bool]:
    warmed: dict[str, bool] = {}
    page = context.new_page()
    try:
        ensure_amazon_us_zip(page)
        warmed["amazon"] = True
    except Exception:
        warmed["amazon"] = False
    page.close()
    return warmed


def collect_results(skus: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            locale="en-US",
            timezone_id="America/New_York",
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        context.add_cookies(
            [
                {"name": "lc-main", "value": "en_US", "domain": ".amazon.com", "path": "/"},
                {"name": "i18n-prefs", "value": "USD", "domain": ".amazon.com", "path": "/"},
                {"name": "sp-cdn", "value": "L5Z9:US", "domain": ".amazon.com", "path": "/"},
            ]
        )

        warmed = warm_context(context)
        page = context.new_page()
        total = sum(len(item["retailers"]) for item in skus)
        index = 0
        last_retailer: str | None = None

        for item in skus:
            sku_id = item["sku_id"]
            product = item["product"]
            for retailer, info in item["retailers"].items():
                index += 1
                url = info["url"]
                print(f"[{index}/{total}] {sku_id} / {retailer} ...", flush=True)

                if last_retailer == "amazon" and retailer != "amazon":
                    warmed["amazon"] = False
                last_retailer = retailer

                scraped = scrape_page(page, retailer, url, warmed)
                if retailer == "amazon":
                    warmed["amazon"] = True
                if retailer == "newegg":
                    warmed["newegg"] = True
                if retailer == "walmart":
                    warmed["walmart"] = True
                results.append(
                    {
                        "sku_id": sku_id,
                        "product": product,
                        "retailer": retailer,
                        "url": url,
                        "name": scraped.name,
                        "price": scraped.price,
                        "availability": scraped.availability,
                        "rating": scraped.rating,
                        "status": scraped.status,
                    }
                )
                time.sleep(0.5)

        page.close()
        browser.close()
    return results


def extract_retailer(url: str) -> str | None:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return None
    if host.startswith("www."):
        host_no_www = host[4:]
    else:
        host_no_www = host
    return RETAILER_DOMAINS.get(host) or RETAILER_DOMAINS.get(host_no_www)


def normalize_listing_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    clean = parsed._replace(query="", fragment="")
    return urllib.parse.urlunparse(clean).rstrip("/")


def search_new_listings(skus: list[dict[str, Any]]) -> list[dict[str, Any]]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    listings: list[dict[str, Any]] = []

    for item in skus:
        sku_id = item["sku_id"]
        product = item["product"]
        existing_urls = {
            normalize_listing_url(info["url"]).lower()
            for info in item["retailers"].values()
        }

        found: list[dict[str, str]] = []
        seen_urls: set[str] = set()

        try:
            response = session.post(
                "https://lite.duckduckgo.com/lite/",
                data={"q": f"{product} buy price"},
                timeout=20,
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "lxml")
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if not href.startswith("http"):
                    continue
                retailer = extract_retailer(href)
                if not retailer:
                    continue
                normalized = normalize_listing_url(href).lower()
                if normalized in seen_urls or normalized in existing_urls:
                    continue
                seen_urls.add(normalized)
                found.append(
                    {
                        "retailer": retailer,
                        "url": normalize_listing_url(href),
                        "title": link.get_text(strip=True)[:200],
                    }
                )
                if len(found) >= 5:
                    break
        except Exception as exc:
            print(f"Search failed for {sku_id}: {exc}", file=sys.stderr)

        listings.append(
            {
                "sku_id": sku_id,
                "product": product,
                "new_retailers": found,
            }
        )
        time.sleep(1)

    return listings


def main() -> None:
    skus = load_skus()
    print("Collecting prices from retailer pages...")
    results = collect_results(skus)
    with RESULTS_PATH.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(results)} records to {RESULTS_PATH}")

    print("Searching for additional retailer listings...")
    listings = search_new_listings(skus)
    with NEW_LISTINGS_PATH.open("w", encoding="utf-8") as f:
        json.dump(listings, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(listings)} product searches to {NEW_LISTINGS_PATH}")

    complete = sum(1 for row in results if row.get("status") == "ok")
    print(f"\nSuccessfully collected all four fields for {complete}/{len(results)} pages.")


if __name__ == "__main__":
    main()
