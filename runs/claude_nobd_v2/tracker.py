#!/usr/bin/env python3
"""
Competitor Price Tracker — scrapes 41 product pages across 5 retailers.
Outputs: results.json, new_listings.json

Usage:
    python3 tracker.py
"""

import json, re, subprocess, sys, time
from pathlib import Path
from urllib.parse import urlparse, quote_plus, unquote

import requests
from bs4 import BeautifulSoup

BASE_DIR          = Path(__file__).parent
SKUS_FILE         = BASE_DIR / "skus.json"
RESULTS_FILE      = BASE_DIR / "results.json"
NEW_LISTINGS_FILE = BASE_DIR / "new_listings.json"
DASHBOARD_FILE    = BASE_DIR / "dashboard.html"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# ── Helpers ─────────────────────────────────────────────────────────────────

def parse_price(text):
    if text is None:
        return None
    s = str(text).replace(",", "").strip()
    m = re.search(r'\$?\s*(\d{1,5}\.\d{2})', s)
    if not m:
        m = re.search(r'\$\s*(\d{1,5})\b', s)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def schema_avail(url):
    if not url:
        return None
    u = url.lower()
    if "instock" in u or "in_stock" in u:
        return "In Stock"
    if "outofstock" in u or "out_of_stock" in u:
        return "Out of Stock"
    if "limitedavailability" in u:
        return "Limited Availability"
    if "preorder" in u or "presale" in u:
        return "Pre-Order"
    return None


def json_ld_product(soup):
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("@type") == "Product":
                return node
            for g in node.get("@graph", []):
                if isinstance(g, dict) and g.get("@type") == "Product":
                    return g
    return None


def from_json_ld(ld):
    name = ld.get("name")
    price = None
    avail = None
    rating = None
    offers = ld.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if isinstance(offers, dict):
        raw_price = offers.get("price")
        if raw_price is not None:
            price = parse_price(str(raw_price))
        avail = schema_avail(offers.get("availability", ""))
    ar = ld.get("aggregateRating") or {}
    if isinstance(ar, dict):
        rv = ar.get("ratingValue")
        if rv is not None:
            rating = str(rv)
    return name, price, avail, rating


# ── Fetchers ─────────────────────────────────────────────────────────────────

def fetch_requests(url, timeout=20):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            return r.text
        return None
    except Exception:
        return None


def fetch_curl(url, timeout=25):
    """Fetch via curl —  bypasses HTTP/2 issues and uses Chrome TLS profile."""
    try:
        result = subprocess.run(
            [
                "curl", "-s", "-L", "--http1.1",
                "--max-time", str(timeout),
                "--compressed",
                "-A", UA,
                "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "-H", "Accept-Language: en-US,en;q=0.9",
                "-H", "DNT: 1",
                "--", url,
            ],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if result.returncode == 0 and len(result.stdout) > 500:
            return result.stdout
    except Exception:
        pass
    return None


def fetch_playwright(url, wait_sel=None, timeout_ms=35000):
    """Try Playwright headless Chrome; returns HTML or None.

    For Amazon URLs the browser first visits amazon.com and sets US zip 10001
    so that prices are shown in USD rather than the local currency.
    """
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage",
                      "--disable-blink-features=AutomationControlled"],
            )
            ctx = browser.new_context(
                user_agent=UA,
                viewport={"width": 1280, "height": 900},
                locale="en-US",
                timezone_id="America/New_York",
                extra_http_headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            page = ctx.new_page()

            # ── Amazon: set US delivery location so prices show in USD ──────
            if "amazon.com" in url:
                try:
                    page.goto("https://www.amazon.com/", wait_until="domcontentloaded",
                              timeout=20_000)
                    page.wait_for_timeout(2000)
                    loc = page.query_selector("#nav-global-location-popover-link")
                    if loc:
                        loc.click()
                        page.wait_for_timeout(1500)
                        zip_inp = page.query_selector("#GLUXZipUpdateInput")
                        if zip_inp:
                            zip_inp.fill("10001")
                            btn = page.query_selector(
                                "#GLUXZipUpdate input[type='submit'], button.a-button-text"
                            )
                            if btn:
                                btn.click()
                            else:
                                page.keyboard.press("Enter")
                            page.wait_for_timeout(2000)
                except Exception:
                    pass  # best-effort; continue to product page

            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if wait_sel:
                try:
                    page.wait_for_selector(wait_sel, timeout=8000)
                except Exception:
                    pass
            else:
                page.wait_for_timeout(3000)
            html = page.content()
            browser.close()
            return html
    except Exception:
        return None


def fetch_url(url, retailer):
    """Smart fetch: choose strategy by retailer."""
    domain = urlparse(url).netloc.lower()

    # BestBuy blocks Playwright (HTTP/2 errors) — use curl only
    if "bestbuy" in domain:
        html = fetch_curl(url)
        if html and len(html) > 2000:
            return html
        # Try requests as last resort
        html = fetch_requests(url)
        return html

    # For other retailers, try Playwright first, then curl, then requests
    wait_sel = None
    if "amazon" in domain:
        wait_sel = "#productTitle, #corePrice_feature_div"
    elif "target" in domain:
        wait_sel = "[data-test='product-price'], [data-test='product-title']"
    elif "newegg" in domain:
        wait_sel = "h1.product-title, li.price-current"

    html = fetch_playwright(url, wait_sel=wait_sel)
    if html and len(html) > 2000:
        return html

    html = fetch_curl(url)
    if html and len(html) > 2000:
        return html

    return fetch_requests(url)


# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_amazon(soup):
    name, price, avail, rating = None, None, None, None
    ld = json_ld_product(soup)
    if ld:
        name, price, avail, rating = from_json_ld(ld)
    if not name:
        el = soup.select_one("#productTitle")
        if el:
            name = el.get_text(" ", strip=True)
    if price is None:
        for sel in [
            "#corePrice_feature_div .a-offscreen",
            "#corePriceDisplay_desktop_feature_div .a-offscreen",
            ".priceToPay .a-offscreen",
            "#price_inside_buybox",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
        ]:
            el = soup.select_one(sel)
            if el:
                txt = el.get("content") or el.get_text(strip=True)
                p = parse_price(txt)
                if p and 1.0 <= p <= 10000.0:
                    price = p
                    break
    if not avail:
        el = soup.select_one("#availability")
        if el:
            t = el.get_text(" ", strip=True).lower()
            if "in stock" in t:
                avail = "In Stock"
            elif "unavailable" in t or "out of stock" in t:
                avail = "Out of Stock"
            elif t.strip():
                avail = el.get_text(strip=True)[:80]
        if not avail and (soup.select_one("#add-to-cart-button") or soup.select_one("#buy-now-button")):
            avail = "In Stock"
    if not rating:
        el = soup.select_one("#acrPopover")
        if el:
            t = str(el.get("title") or "") or el.get_text(strip=True)
            m = re.search(r"([\d.]+)\s*out of", t)
            if m:
                rating = m.group(1)
        if not rating:
            for sel in [".a-icon-star-small .a-icon-alt", ".a-icon-star .a-icon-alt"]:
                el = soup.select_one(sel)
                if el:
                    m = re.search(r"([\d.]+)", el.get_text(strip=True))
                    if m:
                        rating = m.group(1)
                        break
    return {"name": name, "price": price, "availability": avail, "rating": rating}


def parse_bestbuy(soup):
    name, price, avail, rating = None, None, None, None
    ld = json_ld_product(soup)
    if ld:
        name, price, avail, rating = from_json_ld(ld)
    if not name:
        for sel in ["h1.heading-5", "h1.sku-title", "h1[class*='heading']", ".sku-title", "h1"]:
            el = soup.select_one(sel)
            if el:
                name = el.get_text(strip=True)
                break
    if price is None:
        for sel in [
            ".priceView-customer-price span[aria-hidden='true']",
            ".priceView-hero-price .sr-only",
            "div.priceView-customer-price",
        ]:
            el = soup.select_one(sel)
            if el:
                price = parse_price(el.get_text(strip=True))
                if price:
                    break
    if not avail:
        if soup.select_one("[class*='soldOut'], [class*='SoldOut']"):
            avail = "Out of Stock"
        elif soup.select_one("button.add-to-cart-button, button[data-button-state='ADD_TO_CART']"):
            avail = "In Stock"
    if not rating:
        for sel in [".c-review-average", ".ugc-new-average-overall-rating span"]:
            el = soup.select_one(sel)
            if el:
                t = el.get_text(strip=True)
                if t:
                    rating = t
                    break
    return {"name": name, "price": price, "availability": avail, "rating": rating}


def parse_walmart(soup):
    name, price, avail, rating = None, None, None, None
    # __NEXT_DATA__ first — richest source
    nd = soup.select_one("script#__NEXT_DATA__")
    if nd:
        try:
            raw = json.loads(nd.string or "{}")
            prod = (raw.get("props", {}).get("pageProps", {})
                    .get("initialData", {}).get("data", {}).get("product", {}))
            if prod:
                name = prod.get("name")
                pi = prod.get("priceInfo") or {}
                cp = pi.get("currentPrice") or {}
                p = cp.get("price") or cp.get("priceString")
                if p is not None:
                    price = parse_price(str(p))
                av = prod.get("availabilityStatus", "")
                if av:
                    avail = "In Stock" if av.lower() in ("in_stock", "available", "available_for_delivery") else (
                            "Out of Stock" if "out" in av.lower() else av)
                rv = prod.get("averageRating")
                if rv is not None:
                    rating = str(rv)
        except Exception:
            pass
    # JSON-LD fallback
    if not name or price is None:
        ld = json_ld_product(soup)
        if ld:
            ln, lp, la, lr = from_json_ld(ld)
            name = name or ln
            price = price if price is not None else lp
            avail = avail or la
            rating = rating or lr
    if not name:
        for sel in ["h1[itemprop='name']", "[data-automation='product-title']", ".prod-ProductTitle"]:
            el = soup.select_one(sel)
            if el:
                name = el.get_text(strip=True)
                break
    return {"name": name, "price": price, "availability": avail, "rating": rating}


def parse_target(soup):
    name, price, avail, rating = None, None, None, None
    ld = json_ld_product(soup)
    if ld:
        name, price, avail, rating = from_json_ld(ld)
    if not name:
        for sel in ["h1[data-test='product-title']", "[data-test='product-title']", "h1"]:
            el = soup.select_one(sel)
            if el:
                name = el.get_text(strip=True)
                break
    if price is None:
        for sel in ["[data-test='product-price']", "[data-test='current-price']",
                    "span[class*='Price']", "[class*='CurrentPrice']"]:
            el = soup.select_one(sel)
            if el:
                price = parse_price(el.get_text(strip=True))
                if price:
                    break
    if not avail:
        # "Add to cart" text present → product is purchasable
        for node in soup.find_all(string=re.compile("Add to cart", re.I)):
            avail = "In Stock"
            break
        if not avail:
            for sel in ["[data-test='fulfillment-cell']", "[class*='availabilityLabel']",
                        "[class*='fulfillmentOptions']"]:
                el = soup.select_one(sel)
                if el:
                    t = el.get_text(" ", strip=True).lower()
                    if any(x in t for x in ("in stock", "pick up", "delivery",
                                            "ships", "arrives by")):
                        avail = "In Stock"
                    elif any(x in t for x in ("unavailable", "out of stock")):
                        avail = "Out of Stock"
                    else:
                        avail = el.get_text(strip=True)[:60]
                    break
        if not avail and soup.select_one("[data-test='addToCartButton'], [data-test='shippingButton']"):
            avail = "In Stock"
    if not rating:
        # "X out of 5 stars" text nodes (Playwright-rendered pages)
        for node in soup.find_all(string=re.compile(r"[\d.]+ out of 5 stars")):
            m = re.search(r"([\d.]+) out of 5 stars", str(node))
            if m:
                rating = m.group(1)
                break
        if not rating:
            for sel in ["[class*='RatingValue']", "[data-test='ratings']",
                        "button[class*='ratingStars']"]:
                el = soup.select_one(sel)
                if el:
                    m = re.search(r"([\d.]+)", el.get_text(strip=True))
                    if m:
                        rating = m.group(1)
                        break
    return {"name": name, "price": price, "availability": avail, "rating": rating}


def parse_newegg(soup):
    name, price, avail, rating = None, None, None, None
    ld = json_ld_product(soup)
    if ld:
        name, price, avail, rating = from_json_ld(ld)
    if not name:
        el = soup.select_one("h1.product-title")
        if el:
            name = el.get_text(strip=True)
    if price is None:
        el = soup.select_one("li.price-current")
        if el:
            strong = el.find("strong")
            sup = el.find("sup")
            if strong:
                dollars = strong.get_text(strip=True).replace(",", "")
                cents = (sup.get_text(strip=True) if sup else "00").ljust(2, "0")
                try:
                    price = float(f"{dollars}.{cents}")
                except ValueError:
                    price = parse_price(el.get_text(strip=True))
            else:
                price = parse_price(el.get_text(strip=True))
    if not avail:
        el = soup.select_one("div.product-inventory strong")
        if el:
            t = el.get_text(strip=True).lower()
            avail = "In Stock" if "in stock" in t else ("Out of Stock" if "out" in t else el.get_text(strip=True))
        if not avail:
            btn = soup.select_one("button.btn-primary.btn-message")
            if btn:
                t = btn.get_text(strip=True).lower()
                if "add to cart" in t:
                    avail = "In Stock"
                elif "sold out" in t:
                    avail = "Out of Stock"
    if not rating:
        for sel in [".product-rating .rating", "a.item-rating"]:
            el = soup.select_one(sel)
            if el:
                t = str(el.get("title") or "") or el.get_text(strip=True)
                m = re.search(r"([\d.]+)", t)
                if m:
                    rating = m.group(1)
                    break
    return {"name": name, "price": price, "availability": avail, "rating": rating}


PARSERS = {
    "amazon.com":  parse_amazon,
    "bestbuy.com": parse_bestbuy,
    "walmart.com": parse_walmart,
    "target.com":  parse_target,
    "newegg.com":  parse_newegg,
}


def get_parser(url):
    domain = urlparse(url).netloc.replace("www.", "")
    for key, fn in PARSERS.items():
        if key in domain:
            return fn
    return None


# ── New-listings search ───────────────────────────────────────────────────────

def search_new_listings(product_name, existing_urls, max_results=5):
    existing_domains = {urlparse(u).netloc.replace("www.", "") for u in existing_urls}
    skip = {
        "google.", "bing.", "yahoo.", "duckduckgo.", "reddit.", "youtube.",
        "wikipedia.", "twitter.", "facebook.", "instagram.", "tiktok.",
        "pinterest.", "ebay.com", "amazon.com", "walmart.com",
        "bestbuy.com", "target.com", "newegg.com",
    }
    query = f"{product_name} buy"
    found = []
    seen = set(existing_domains)
    for attempt_url in [
        f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}",
        f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
    ]:
        try:
            resp = requests.get(
                attempt_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1)",
                         "Accept-Language": "en-US,en;q=0.9"},
                timeout=12,
            )
            if resp.status_code not in (200, 202):
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.select("a.result-link, a.result__a, .results a"):
                raw = str(a.get("href") or "")
                if "uddg=" in raw:
                    m = re.search(r"uddg=([^&]+)", raw)
                    if m:
                        raw = unquote(m.group(1))
                if not raw.startswith("http"):
                    continue
                domain = urlparse(raw).netloc.replace("www.", "")
                if domain in seen:
                    continue
                if any(domain.startswith(s) or s in domain for s in skip):
                    continue
                seen.add(domain)
                found.append(raw)
                if len(found) >= max_results:
                    break
            if found:
                break
        except Exception as exc:
            print(f"    search error: {exc}")
    return found


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Competitor Price Tracker")
    print("=" * 60)

    skus = json.loads(SKUS_FILE.read_text())
    total = sum(len(s["retailers"]) for s in skus)
    print(f"  Products: {len(skus)}  |  Pages: {total}")
    print()

    results = []
    new_listings = []

    for sku in skus:
        sku_id = sku["sku_id"]
        product = sku["product"]
        print(f"[{sku_id}] {product}")

        existing_urls = [info["url"] for info in sku["retailers"].values()]

        for retailer, info in sku["retailers"].items():
            url = info["url"]
            sys.stdout.write(f"  {retailer:10s} → ")
            sys.stdout.flush()

            record = {
                "sku_id": sku_id, "product": product,
                "retailer": retailer, "url": url,
                "name": None, "price": None, "availability": None,
                "rating": None, "status": "ok",
            }

            try:
                html = fetch_url(url, retailer)
                if not html or len(html) < 500:
                    record["status"] = "fetch failed"
                else:
                    parser = get_parser(url)
                    if parser:
                        fields = parser(BeautifulSoup(html, "html.parser"))
                        record.update(fields)
                    else:
                        record["status"] = "no parser"
            except Exception as exc:
                record["status"] = f"error: {str(exc)[:80]}"

            if record["status"] == "ok":
                missing = [k for k in ("name", "price", "availability", "rating")
                           if record[k] is None]
                if missing:
                    record["status"] = f"partial: missing {', '.join(missing)}"

            icon = "✓" if record["status"] == "ok" else "~" if record["status"].startswith("partial") else "✗"
            price_s = f"${record['price']:.2f}" if record["price"] else "None"
            print(f"{icon} price={price_s:9s} rating={record['rating']} status={record['status'][:40]}")
            results.append(record)
            time.sleep(1.5)

        # new listings
        sys.stdout.write(f"  searching new listings ... ")
        sys.stdout.flush()
        new_urls = search_new_listings(product, existing_urls)
        print(f"{len(new_urls)} found")
        new_listings.append({
            "sku_id": sku_id,
            "product": product,
            "new_retailer_urls": new_urls,
        })
        print()

    RESULTS_FILE.write_text(json.dumps(results, indent=2))
    NEW_LISTINGS_FILE.write_text(json.dumps(new_listings, indent=2))
    build_dashboard(results)

    ok = sum(1 for r in results if r["status"] == "ok")
    partial = sum(1 for r in results if r["status"].startswith("partial"))
    errors = sum(1 for r in results if not r["status"].startswith("partial") and r["status"] != "ok")

    print("=" * 60)
    print(f"  SUMMARY: {ok}/{total} pages had all 4 fields")
    print(f"  Partial: {partial}  |  Failed: {errors}")
    print(f"  Output:  {RESULTS_FILE.name}, {NEW_LISTINGS_FILE.name}, {DASHBOARD_FILE.name}")
    print("=" * 60)

    return ok


# ── Dashboard ─────────────────────────────────────────────────────────────────

def build_dashboard(results):
    """Embed results into a self-contained dashboard.html."""
    skus_map = {}
    all_retailers = []
    for r in results:
        sid, ret = r["sku_id"], r["retailer"]
        if sid not in skus_map:
            skus_map[sid] = {"product": r["product"], "retailers": {}}
        skus_map[sid]["retailers"][ret] = r
        if ret not in all_retailers:
            all_retailers.append(ret)

    def cheapest(sku_data):
        prices = {k: v["price"] for k, v in sku_data["retailers"].items()
                  if v.get("price") is not None}
        return min(prices, key=prices.__getitem__) if prices else None

    ret_headers = "".join(f"<th>{r.capitalize()}</th>" for r in all_retailers)

    rows = ""
    for sid, sd in skus_map.items():
        cheap = cheapest(sd)
        cells = ""
        for ret in all_retailers:
            rec = sd["retailers"].get(ret)
            if rec is None:
                cells += "<td class='na'>—</td>"
                continue
            price, avail = rec.get("price"), rec.get("availability") or ""
            rating, status = rec.get("rating") or "", rec.get("status", "")
            if "blocked" in status or "fetch failed" in status:
                cells += f"<td class='blocked' title='{status}'>⊘</td>"
            elif price is None:
                cells += f"<td class='miss' title='{status}'><span class='sub'>{status[:40]}</span></td>"
            else:
                is_best = ret == cheap
                a_cls = "av-ok" if any(w in avail.lower() for w in
                         ("stock", "arrives", "ships", "delivery")) else "av-no"
                cells += (
                    f"<td class='pc {'best' if is_best else ''}'>"
                    f"<b>${price:.2f}</b>{'<span class=\"badge\">BEST</span>' if is_best else ''}"
                    f"<br><span class='sub {a_cls}'>{avail or '—'}</span>"
                    f"<br><span class='sub'>{'★ '+rating if rating else ''}</span>"
                    f"</td>"
                )
        rows += f"<tr><td class='sid'>{sid}</td><td class='prod'>{sd['product']}</td>{cells}</tr>\n"

    data_js = json.dumps(results, indent=2)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Price Tracker Dashboard</title>
<style>
:root{{--bg:#0f172a;--sf:#1e293b;--bd:#334155;--tx:#e2e8f0;--sub:#94a3b8;
  --ac:#38bdf8;--gn:#4ade80;--rd:#f87171;--yw:#fbbf24;--bb:#064e3b;--bc:#059669;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--tx);font:14px system-ui,sans-serif;padding:24px;}}
h1{{font-size:20px;color:var(--ac);margin-bottom:4px;}}
.meta{{color:var(--sub);font-size:12px;margin-bottom:16px;}}
.ctrl{{display:flex;gap:12px;align-items:center;margin-bottom:16px;flex-wrap:wrap;}}
input[type=search]{{padding:7px 12px;border-radius:8px;border:1px solid var(--bd);
  background:var(--sf);color:var(--tx);font-size:13px;width:260px;}}
.legend{{font-size:12px;color:var(--sub);display:flex;gap:14px;}}
.legend span{{display:flex;align-items:center;gap:4px;}}
.dot{{width:9px;height:9px;border-radius:2px;display:inline-block;}}
.dot-b{{background:var(--bc);}} .dot-x{{background:#44403c;}}
.wrap{{overflow-x:auto;border-radius:10px;border:1px solid var(--bd);}}
table{{width:100%;border-collapse:collapse;}}
th{{background:var(--sf);color:var(--ac);text-align:left;padding:9px 13px;
  border-bottom:2px solid var(--bd);white-space:nowrap;font-size:11px;
  text-transform:uppercase;letter-spacing:.05em;font-weight:600;}}
td{{padding:9px 13px;border-bottom:1px solid var(--bd);vertical-align:top;}}
tr:last-child td{{border-bottom:none;}}
tr:hover td{{background:rgba(255,255,255,.025);}}
.sid{{font-family:monospace;color:var(--sub);white-space:nowrap;}}
.prod{{font-weight:500;max-width:200px;}}
.pc{{min-width:120px;}} .pc b{{font-size:15px;}}
.best{{background:var(--bb)!important;border-left:3px solid var(--bc);}}
.badge{{background:var(--bc);color:#d1fae5;font-size:9px;font-weight:700;
  padding:1px 5px;border-radius:3px;margin-left:5px;vertical-align:middle;}}
.sub{{font-size:11px;color:var(--sub);}}
.av-ok{{color:var(--gn);}} .av-no{{color:var(--rd);}}
.blocked{{color:#57534e;background:#1c1917;text-align:center;font-size:13px;}}
.miss{{color:var(--sub);font-size:12px;}}
.na{{background:var(--sf);color:#334155;text-align:center;}}
.cards{{margin-top:20px;display:flex;gap:14px;flex-wrap:wrap;}}
.card{{background:var(--sf);border:1px solid var(--bd);border-radius:10px;padding:12px 18px;min-width:130px;}}
.cl{{font-size:10px;color:var(--sub);text-transform:uppercase;letter-spacing:.05em;}}
.cv{{font-size:26px;font-weight:700;margin-top:3px;}}
.gn{{color:var(--gn);}} .yw{{color:var(--yw);}} .rd{{color:var(--rd);}} .ac{{color:var(--ac);}}
.ts{{color:var(--sub);font-size:11px;margin-top:20px;text-align:right;}}
</style></head>
<body>
<h1>🏷️ Competitor Price Tracker</h1>
<p class="meta">10 products · 41 pages · Amazon, Best Buy, Walmart, Target, Newegg</p>
<div class="ctrl">
  <input type="search" id="q" placeholder="Filter products…" oninput="filter()">
  <div class="legend">
    <span><span class="dot dot-b"></span>Cheapest</span>
    <span><span class="dot dot-x"></span>Blocked</span>
  </div>
</div>
<div class="wrap"><table id="tbl">
<thead><tr><th>SKU</th><th>Product</th>{ret_headers}</tr></thead>
<tbody>{rows}</tbody>
</table></div>
<div class="cards" id="cards"></div>
<p class="ts" id="ts"></p>
<script>
const R={data_js};
(()=>{{
  const ok=R.filter(r=>r.status==='ok').length;
  const p=R.filter(r=>r.status.startsWith('partial')).length;
  const b=R.filter(r=>r.status.includes('blocked')||r.status==='fetch failed').length;
  const cards=[
    ['Total Pages',R.length,'ac'],['Full Data',ok,'gn'],['Partial',p,'yw'],['Blocked',b,'rd']
  ];
  const d=document.getElementById('cards');
  cards.forEach(([l,v,c])=>{{d.innerHTML+=`<div class="card"><div class="cl">${{l}}</div><div class="cv ${{c}}">${{v}}</div></div>`;  }});
  document.getElementById('ts').textContent='Collected: '+new Date().toLocaleString();
}})();
function filter(){{
  const q=document.getElementById('q').value.toLowerCase();
  document.querySelectorAll('#tbl tbody tr').forEach(r=>{{
    r.style.display=r.textContent.toLowerCase().includes(q)?'':'none';
  }});
}}
</script>
</body></html>"""
    DASHBOARD_FILE.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    ok = main()
    sys.exit(0)
