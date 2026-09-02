#!/usr/bin/env python3
"""
Competitor price tracker.

Reads skus.json (never modified), visits every retailer product page listed
there, and extracts product name / price / availability / rating from each
page. Writes results.json with one record per page.

Also refreshes new_listings.json (a DuckDuckGo web search per product for
additional retailer URLs not already present in skus.json) and leaves
dashboard.html untouched (it reads results.json at load time in the browser).

Usage:
    python3 scrape.py

Requires: requests, beautifulsoup4, lxml, seleniumbase (already installed in
this environment). SeleniumBase's undetected-chromedriver (UC) mode is used
for retailers that actively block plain HTTP clients (Amazon, Best Buy,
Target, Newegg). Walmart is fetched with plain requests since it serves full
data without a browser.
"""

import json
import re
import sys
import time
import traceback
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
SKUS_PATH = BASE_DIR / "skus.json"
RESULTS_PATH = BASE_DIR / "results.json"
NEW_LISTINGS_PATH = BASE_DIR / "new_listings.json"

REQUESTS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

# Retailers that need a real (stealth) browser because they block plain HTTP
# clients with bot-detection (Akamai / PerimeterX / captchas).
BROWSER_RETAILERS = {"bestbuy", "amazon", "target", "newegg"}


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def load_skus():
    with open(SKUS_PATH) as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Per-retailer extraction
# --------------------------------------------------------------------------

def _camel_to_words(s):
    return re.sub(r"(?<!^)(?=[A-Z])", " ", s).strip()


def extract_bestbuy(html):
    out = {"name": None, "price": None, "availability": None, "rating": None, "note": None}
    blocks = re.findall(r'application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
    product = None
    for b in blocks:
        try:
            d = json.loads(b)
        except Exception:
            continue
        if isinstance(d, dict) and d.get("@type") == "Product":
            product = d
            break
    if not product:
        # Best Buy omits the Product JSON-LD block entirely when an item has
        # no purchasable offer (e.g. discontinued in new condition); fall
        # back to scraping name/rating directly, and flag it unavailable.
        soup = BeautifulSoup(html, "lxml")
        h1 = soup.select_one("h1")
        if h1:
            out["name"] = h1.get_text(strip=True)
        text = soup.get_text(" ", strip=True)
        m = re.search(r"([\d.]+)\s*out of 5 stars", text)
        if m:
            try:
                out["rating"] = float(m.group(1))
            except ValueError:
                pass
        if re.search(r"no longer available|sold out|out of stock", text, re.I):
            out["availability"] = "Out of Stock"
            out["note"] = "no longer available in new condition (no product JSON-LD / no active offer)"
        else:
            out["note"] = "no product JSON-LD found"
        return out

    out["name"] = product.get("name")
    agg = product.get("aggregateRating") or {}
    if agg.get("ratingValue") is not None:
        try:
            out["rating"] = float(agg["ratingValue"])
        except (TypeError, ValueError):
            pass

    offers = product.get("offers")
    offer = None
    if isinstance(offers, list) and offers:
        offer = next(
            (o for o in offers if "NewCondition" in (o.get("itemCondition") or "")),
            offers[0],
        )
    elif isinstance(offers, dict):
        offer = offers

    if offer:
        price = offer.get("price")
        if price is not None:
            try:
                out["price"] = float(price)
            except (TypeError, ValueError):
                pass
        avail = offer.get("availability")
        if avail:
            out["availability"] = _camel_to_words(avail.rsplit("/", 1)[-1])
    return out


def extract_amazon(html):
    out = {"name": None, "price": None, "availability": None, "rating": None, "note": None}
    soup = BeautifulSoup(html, "lxml")

    title = soup.select_one("#productTitle")
    if title:
        out["name"] = title.get_text(strip=True)

    # Deliberately scoped to known buy-box containers only; a bare
    # ".a-price .a-offscreen" fallback risks grabbing an unrelated price from
    # a "customers also bought" / sponsored carousel elsewhere on the page.
    price_selectors = [
        "#corePrice_feature_div .a-price .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
        "#apex_desktop .a-price .a-offscreen",
        "#booksHeaderSection .a-price .a-offscreen",
        ".priceToPay .a-offscreen",
        "#price_inside_buybox",
        "#tp_price_block_total_price_ww .a-offscreen",
        "#newBuyBoxPrice",
        # Some buy-box renders leave .a-offscreen empty but still populate this
        # visually-hidden accessibility label with the same price text.
        "#apex-pricetopay-accessibility-label",
    ]

    def _parse_price_text(txt):
        # Prefer an explicit "$1,234.56" match, which is unambiguous even if
        # the surrounding text has other words (e.g. "with X% savings").
        m = re.search(r"\$\s*([\d,]+\.\d+)", txt)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                return None
        # No "$" found: only accept a bare number if there's no currency-code
        # style text (e.g. "INR4,660.96") suggesting a non-USD price.
        if re.search(r"[A-Za-z]{2,}", txt.replace(",", "")):
            return None
        m = re.search(r"[\d,]+\.\d+", txt)
        if m:
            try:
                return float(m.group(0).replace(",", ""))
            except ValueError:
                return None
        return None

    for sel in price_selectors:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            price = _parse_price_text(el.get_text(strip=True))
            if price is not None:
                out["price"] = price
                break

    if out["price"] is None:
        # Fallback: reconstruct from the visually-hidden whole/fraction spans
        # inside the buy-box price widget, used when .a-offscreen is empty.
        # Only trust it if the adjacent symbol span reads "$" (USD); Amazon's
        # geolocated INR pricing puts the currency in a separate "INR" text
        # node rather than in .a-price-symbol, so this also guards against
        # non-USD prices slipping through here.
        for container_sel in ("#corePriceDisplay_desktop_feature_div", "#corePrice_feature_div", "#apex_desktop", ".priceToPay"):
            container = soup.select_one(container_sel)
            if not container:
                continue
            price_span = container.select_one(".a-price:has(.a-price-whole)") or container.select_one(".a-price")
            if not price_span:
                continue
            whole = price_span.select_one(".a-price-whole")
            fraction = price_span.select_one(".a-price-fraction")
            symbol = price_span.select_one(".a-price-symbol")
            if whole and fraction and symbol and symbol.get_text(strip=True) == "$":
                whole_txt = re.sub(r"[^\d]", "", whole.get_text())
                frac_txt = re.sub(r"[^\d]", "", fraction.get_text())
                if whole_txt and frac_txt:
                    try:
                        out["price"] = float(f"{whole_txt}.{frac_txt}")
                        break
                    except ValueError:
                        pass

    avail_el = soup.select_one("#availability span")
    if avail_el and avail_el.get_text(strip=True):
        out["availability"] = avail_el.get_text(strip=True)
    elif soup.select_one("#outOfStockBuyBox_feature_div"):
        out["availability"] = "Out of Stock"
        out["note"] = "out of stock (no featured offer / no seller currently)"
    elif soup.find(string=re.compile("See All Buying Options", re.I)):
        out["note"] = "no single-seller buy box (see all buying options)"

    rating_el = soup.select_one("#acrPopover") or soup.select_one("span.a-icon-alt")
    rating_text = None
    if rating_el:
        rating_text = rating_el.get("title") or rating_el.get_text(strip=True)
    if rating_text:
        m = re.search(r"([\d.]+)\s*out of", rating_text)
        if m:
            try:
                out["rating"] = float(m.group(1))
            except ValueError:
                pass

    if not out["name"]:
        out["note"] = out["note"] or "product title not found (possible bot block)"
    return out


def extract_target(html):
    out = {"name": None, "price": None, "availability": None, "rating": None, "note": None}
    soup = BeautifulSoup(html, "lxml")

    title = soup.select_one('[data-test="product-title"]')
    if title:
        out["name"] = title.get_text(strip=True)

    price_el = soup.select_one('[data-test="product-price"]')
    if price_el:
        m = re.search(r"\$([\d,]+\.\d+)", price_el.get_text(" ", strip=True))
        if m:
            out["price"] = float(m.group(1).replace(",", ""))

    rating_el = soup.select_one('[data-test="rating-stars"]') or soup.select_one('[data-test="ratingFeedbackContainer"]')
    if rating_el:
        m = re.search(r"([\d.]+)\s*out of\s*5", rating_el.get_text(" ", strip=True))
        if m:
            out["rating"] = float(m.group(1))

    fulfillment = soup.select_one('[data-test="@web/AddToCart/FulfillmentSection"]')
    fulfillment_text = fulfillment.get_text(" ", strip=True) if fulfillment else ""
    if re.search(r"out of stock|sold out|unavailable", fulfillment_text, re.I):
        out["availability"] = "Out of Stock"
    elif re.search(r"ready within|arrives by|shipping|pickup|delivery", fulfillment_text, re.I):
        out["availability"] = "In Stock"

    if not out["name"]:
        out["note"] = "product title not found (possible bot block)"
    return out


def extract_newegg(html):
    out = {"name": None, "price": None, "availability": None, "rating": None, "note": None}
    soup = BeautifulSoup(html, "lxml")

    title = soup.select_one("h1.product-title")
    if title:
        out["name"] = title.get_text(strip=True)

    price_box = soup.select_one(".product-price")
    if price_box:
        m = re.search(r"\$<strong>([\d,]+)</strong><sup>(\.\d+)</sup>", str(price_box))
        if m:
            try:
                out["price"] = float(m.group(1).replace(",", "") + m.group(2))
            except ValueError:
                pass

    rating_box = soup.select_one(".product-rating")
    if rating_box:
        i = rating_box.select_one("i.rating")
        if i and i.get("title"):
            m = re.search(r"([\d.]+)\s*out of\s*5", i["title"])
            if m:
                out["rating"] = float(m.group(1))

    page_text = soup.get_text(" ", strip=True)
    if re.search(r"out of stock|sold out", page_text, re.I) and not soup.select_one(".product-buy button.btn-primary"):
        out["availability"] = "Out of Stock"
    elif soup.select_one(".product-buy button.btn-primary, button[title^='Add ']"):
        out["availability"] = "In Stock"

    if not out["name"]:
        out["note"] = "product title not found (possible bot block / captcha)"
    return out


def _dig(d, *path, default=None):
    cur = d
    for key in path:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        elif isinstance(cur, list) and isinstance(key, int) and -len(cur) <= key < len(cur):
            cur = cur[key]
        else:
            return default
    return cur


def _find_walmart_product(data):
    direct = _dig(data, "props", "pageProps", "initialData", "data", "product")
    if isinstance(direct, dict) and "priceInfo" in direct:
        return direct

    def walk(node, depth=0):
        if depth > 12 or not isinstance(node, (dict, list)):
            return None
        if isinstance(node, dict):
            if "priceInfo" in node and "availabilityStatus" in node:
                return node
            for v in node.values():
                found = walk(v, depth + 1)
                if found:
                    return found
        elif isinstance(node, list):
            for v in node[:50]:
                found = walk(v, depth + 1)
                if found:
                    return found
        return None

    return walk(data)


def extract_walmart_from_json(data):
    out = {"name": None, "price": None, "availability": None, "rating": None, "note": None}
    product = _find_walmart_product(data)
    if not product:
        out["note"] = "product data block not found in page"
        return out

    out["name"] = product.get("name")
    status = product.get("availabilityStatus")
    if status:
        out["availability"] = status.replace("_", " ").title()
    rating = product.get("averageRating")
    if rating is not None:
        try:
            out["rating"] = float(rating)
        except (TypeError, ValueError):
            pass
    price = _dig(product, "priceInfo", "currentPrice", "price")
    if price is not None:
        try:
            out["price"] = float(price)
        except (TypeError, ValueError):
            pass
    return out


def fetch_walmart(url, session):
    try:
        r = session.get(url, headers=REQUESTS_HEADERS, timeout=25)
    except Exception as e:
        return None, f"request failed: {e}"
    if r.status_code != 200:
        return None, f"http {r.status_code}"
    return extract_walmart_html(r.text)


def extract_walmart_html(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None, "no __NEXT_DATA__ block (possible bot block)"
    try:
        data = json.loads(m.group(1))
    except Exception as e:
        return None, f"json parse failed: {e}"
    return data, None


def extract_walmart(html):
    """Adapter so walmart can also run through the browser-fetch pipeline."""
    data, err = extract_walmart_html(html)
    if err:
        return {"name": None, "price": None, "availability": None, "rating": None, "note": err}
    return extract_walmart_from_json(data)


# --------------------------------------------------------------------------
# Browser-based fetch (SeleniumBase UC mode) for bot-protected retailers
# --------------------------------------------------------------------------

EXTRACTORS = {
    "bestbuy": extract_bestbuy,
    "amazon": extract_amazon,
    "target": extract_target,
    "newegg": extract_newegg,
    "walmart": extract_walmart,
}

# A light explicit wait for a key selector before grabbing page source, on
# top of the fixed sleep. Keeps flaky, slow-to-hydrate widgets (e.g. Target's
# client-side fulfillment/price panel) from being captured half-rendered.
WAIT_SELECTORS = {
    "bestbuy": 'script[type="application/ld+json"]',
    "amazon": "#productTitle",
    "target": '[data-test="product-price"], [data-test="@web/AddToCart/FulfillmentSection"]',
    "newegg": "h1.product-title",
}


def _force_amazon_us_locale(sb):
    """This environment's network egress geolocates to India, so Amazon
    defaults to showing INR pricing / India delivery restrictions. Force a
    US ZIP code via the "Deliver to" widget so prices come back in USD."""
    try:
        sb.click("#glow-ingress-block", timeout=5)
        sb.wait_for_element("#GLUXZipUpdateInput", timeout=5)
        sb.type("#GLUXZipUpdateInput", "10001")
        sb.sleep(0.3)
        sb.execute_script('document.querySelector("#GLUXZipUpdate input[type=submit]").click()')
        sb.sleep(1.5)
        sb.execute_script('var b = document.querySelector("#GLUXConfirmClose"); if (b) b.click();')
        sb.sleep(1.5)
    except Exception:
        pass


def _fetch_one_page(sb, retailer, url):
    """Navigate to url with an already-open browser session and return the
    page HTML."""
    if retailer == "walmart":
        # Walmart's PerimeterX challenge gets stuck in a retry loop when
        # combined with the CDP-disconnect reconnect trick; a plain stealth
        # navigation works reliably instead.
        sb.open(url)
    else:
        sb.uc_open_with_reconnect(url, 4)
    if retailer == "amazon":
        _force_amazon_us_locale(sb)
    if retailer == "newegg":
        # Newegg intermittently shows a "click the checkbox" human-verification
        # interstitial. This is a simple bot-check click (no puzzle-solving, no
        # login/credentials) that SeleniumBase's UC mode can pass along with
        # the mouse in a human-like way; try it a couple of times if present.
        for _ in range(2):
            try:
                title = sb.get_title()
            except Exception:
                title = ""
            if "human" not in title.lower():
                break
            try:
                sb.uc_gui_click_captcha()
            except Exception:
                pass
            sb.sleep(3)
    wait_sel = WAIT_SELECTORS.get(retailer)
    if wait_sel:
        try:
            sb.wait_for_element(wait_sel, timeout=8)
        except Exception:
            pass
    sb.sleep(2.5)
    return sb.get_page_source()


def run_browser_scrapes(jobs):
    """jobs: list of dicts with sku_id, product, retailer, url. Returns dict
    keyed by (retailer, url) with extracted fields + status.

    Each job gets its own short-lived browser session. This costs a few
    extra seconds of browser-startup overhead per page, but two retailers
    (Best Buy's Akamai bot-manager, and this environment's headless Chrome
    under sustained multi-minute sessions) both become unreliable once a
    single browser session has been alive / making requests for a while, so
    keeping sessions short is the more robust trade-off for a batch of 41
    pages.
    """
    from seleniumbase import SB

    results = {}
    for job in jobs:
        url = job["url"]
        retailer = job["retailer"]
        key = (retailer, url)
        record = {"name": None, "price": None, "availability": None, "rating": None, "status": None}
        extracted = {}
        nav_error = None

        max_attempts = 3 if retailer in ("target", "newegg") else 2
        for attempt in range(1, max_attempts + 1):
            log(f"[{retailer}] fetching {url} (attempt {attempt}/{max_attempts})")
            nav_error = None
            try:
                # Newegg's human-verification checkbox is clicked via real GUI
                # mouse automation (uc_gui_click_captcha), which only works
                # against an actual on-screen browser window, not a headless one.
                headless = retailer != "newegg"
                with SB(uc=True, headless=headless, test=False) as sb:
                    html = _fetch_one_page(sb, retailer, url)
            except Exception as e:
                nav_error = f"navigation failed: {e}"[:200]
                time.sleep(2)
                continue

            try:
                extracted = EXTRACTORS[retailer](html)
            except Exception as e:
                extracted = {"name": None, "price": None, "availability": None, "rating": None,
                             "note": f"parse error: {e}"}

            all_missing = all(extracted.get(k) is None for k in ("name", "price", "availability", "rating"))
            if not all_missing:
                break
            log(f"    got nothing useful on attempt {attempt}, retrying..." if attempt < max_attempts else "    still nothing after retries, giving up")
            time.sleep(2)

        if nav_error and not extracted:
            record["status"] = nav_error
            results[key] = record
            continue

        record.update({k: extracted.get(k) for k in ("name", "price", "availability", "rating")})
        missing = [k for k in ("name", "price", "availability", "rating") if record[k] is None]
        if not missing:
            record["status"] = "ok"
        else:
            note = extracted.get("note")
            record["status"] = note or f"missing: {', '.join(missing)}"
        results[key] = record
    return results


# --------------------------------------------------------------------------
# Main scrape orchestration
# --------------------------------------------------------------------------

def build_jobs(skus):
    jobs = []
    for sku in skus:
        for retailer, info in sku["retailers"].items():
            jobs.append({
                "sku_id": sku["sku_id"],
                "product": sku["product"],
                "retailer": retailer,
                "url": info["url"],
            })
    return jobs


def scrape_all(skus):
    jobs = build_jobs(skus)
    walmart_jobs = [j for j in jobs if j["retailer"] == "walmart"]

    # First pass: try Walmart with plain requests (fast, usually works).
    session = requests.Session()
    walmart_records = {}
    walmart_needs_browser = []
    for job in walmart_jobs:
        data, err = fetch_walmart(job["url"], session)
        if err:
            log(f"[walmart] requests fetch failed ({err}), will retry via browser: {job['url']}")
            walmart_needs_browser.append(job)
            continue
        extracted = extract_walmart_from_json(data)
        record = {"name": None, "price": None, "availability": None, "rating": None, "status": None}
        record.update({k: extracted.get(k) for k in ("name", "price", "availability", "rating")})
        missing = [k for k in ("name", "price", "availability", "rating") if record[k] is None]
        record["status"] = "ok" if not missing else (extracted.get("note") or f"missing: {', '.join(missing)}")
        walmart_records[job["url"]] = record

    # Anything that needs a real browser: bestbuy/amazon/target/newegg always,
    # plus any walmart pages that got bot-blocked over plain HTTP.
    browser_jobs = [j for j in jobs if j["retailer"] in BROWSER_RETAILERS] + walmart_needs_browser

    browser_results = {}
    if browser_jobs:
        try:
            browser_results = run_browser_scrapes(browser_jobs)
        except Exception as e:
            log(f"browser scraping failed entirely: {e}")
            traceback.print_exc(file=sys.stderr)

    results = []
    for job in jobs:
        record = {
            "sku_id": job["sku_id"],
            "product": job["product"],
            "retailer": job["retailer"],
            "url": job["url"],
            "name": None,
            "price": None,
            "availability": None,
            "rating": None,
            "status": None,
        }

        if job["retailer"] == "walmart" and job["url"] in walmart_records:
            record.update(walmart_records[job["url"]])
        elif job["retailer"] in BROWSER_RETAILERS or job in walmart_needs_browser:
            br = browser_results.get((job["retailer"], job["url"]))
            if br:
                record.update(br)
            else:
                record["status"] = "not scraped (browser session failure)"
        else:
            record["status"] = f"no extractor implemented for retailer '{job['retailer']}'"

        results.append(record)
        log(f"  -> {job['retailer']:8s} {job['sku_id']} status={record['status']}")

    return results


# --------------------------------------------------------------------------
# new_listings.json via web search (DuckDuckGo HTML, no API key needed)
# --------------------------------------------------------------------------

AD_DOMAINS = {"duckduckgo.com"}
NON_RETAIL_DOMAINS = {
    "youtube.com", "reddit.com", "wikipedia.org", "pinterest.com", "facebook.com",
    "twitter.com", "x.com", "instagram.com", "quora.com", "tiktok.com", "linkedin.com",
    # price-comparison / news / tracking sites -- not an actual point of sale
    "klarna.com", "pricehistory.app", "gadgets360.com", "google.com", "bing.com",
}


def existing_domains(sku):
    domains = set()
    for info in sku["retailers"].values():
        domains.add(urlparse(info["url"]).netloc.replace("www.", ""))
    return domains


def _resolve_ddg_href(href):
    """DuckDuckGo's HTML result links are sometimes direct URLs and
    sometimes '/l/?uddg=<url-encoded target>' redirect links."""
    if not href:
        return None
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        from urllib.parse import parse_qs, unquote
        qs = parse_qs(parsed.query)
        target = qs.get("uddg", [None])[0]
        return unquote(target) if target else None
    if href.startswith("http"):
        return href
    return None


def search_new_listings(sb, product_name, existing, limit=5):
    import urllib.parse as up

    q = up.quote(f"{product_name} buy price")
    search_url = f"https://html.duckduckgo.com/html/?q={q}"
    try:
        sb.uc_open_with_reconnect(search_url, 4)
        sb.sleep(2)
        html = sb.get_page_source()
    except Exception as e:
        log(f"search failed for {product_name!r}: {e}")
        return []

    soup = BeautifulSoup(html, "lxml")
    found = []
    seen_domains = set()
    for a in soup.select("a.result__a"):
        url = _resolve_ddg_href(a.get("href"))
        if not url:
            continue
        domain = urlparse(url).netloc.replace("www.", "")
        if not domain or domain in AD_DOMAINS or domain in NON_RETAIL_DOMAINS:
            continue
        if domain in existing or domain in seen_domains:
            continue
        seen_domains.add(domain)
        found.append({"retailer_domain": domain, "url": url, "title": a.get_text(strip=True)})
        if len(found) >= limit:
            break
    return found


def build_new_listings(skus):
    from seleniumbase import SB

    listings = []
    with SB(uc=True, headless=True, test=False) as sb:
        for sku in skus:
            existing = existing_domains(sku)
            found = search_new_listings(sb, sku["product"], existing)
            listings.append({
                "sku_id": sku["sku_id"],
                "product": sku["product"],
                "new_retailer_urls": found,
            })
            log(f"[search] {sku['sku_id']} {sku['product']!r} -> {len(found)} new listing(s)")
            time.sleep(1.0)
    return listings


# --------------------------------------------------------------------------

def main():
    skus = load_skus()

    log("=== Scraping %d product pages ===" % sum(len(s["retailers"]) for s in skus))
    results = scrape_all(skus)
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    log(f"Wrote {RESULTS_PATH}")

    log("=== Searching for new retailer listings ===")
    listings = build_new_listings(skus)
    with open(NEW_LISTINGS_PATH, "w") as f:
        json.dump(listings, f, indent=2)
    log(f"Wrote {NEW_LISTINGS_PATH}")

    total = len(results)
    ok = sum(1 for r in results if r["status"] == "ok")
    log(f"=== Done: {ok}/{total} pages fully collected (all 4 fields) ===")


if __name__ == "__main__":
    main()
