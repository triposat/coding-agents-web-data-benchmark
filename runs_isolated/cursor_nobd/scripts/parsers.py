"""Per-retailer HTML parsers for the competitor price tracker.

Each parser takes raw HTML text (from either a plain HTTP fetch or a
JS-rendered browser fetch) and returns a dict with keys:
    name, price, availability, rating, reason

`reason` is None on success; otherwise a short string describing why some
field(s) could not be extracted. Fields that could not be found are left as
None.
"""
import json
import re

BOT_BLOCK_MARKERS = [
    "robot or human",
    "are you a human",
    "pardon our interruption",
    "access denied",
    "px-captcha",
    "request blocked",
    "captcha-delivery",
    "verify you are a human",
    "additional verification required",
]


def _strip_tags(html_fragment):
    text = re.sub(r"<[^>]+>", " ", html_fragment)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_bot_block(html):
    head = html[:20000].lower()
    for marker in BOT_BLOCK_MARKERS:
        if marker in head:
            return marker
    return None


def empty_result(reason):
    return {"name": None, "price": None, "availability": None, "rating": None, "reason": reason}


# --------------------------------------------------------------------------
# Best Buy: static HTML contains a clean schema.org Product JSON-LD block.
# --------------------------------------------------------------------------
def _parse_bestbuy_from_graphql_blob(html, url):
    """Fallback for Best Buy pages that stream product data as an inline
    GraphQL/RSC JSON payload instead of a schema.org <script id="product-schema">
    block (observed for some out-of-stock / discontinued SKUs)."""
    sku_match = re.search(r'/sku/(\d+)', url or "")
    target_sku = sku_match.group(1) if sku_match else None

    name = None
    m = re.search(r'<title[^>]*>([^<]+)</title>', html)
    if m:
        name = re.sub(r'\s*-\s*Best Buy\s*$', '', m.group(1)).strip()

    price = None
    availability = None
    if target_sku:
        anchor_m = re.search(
            r'"skuId":"' + re.escape(target_sku) + r'","openBoxCondition":(?:null|\d+),"fulfillmentOptions"',
            html,
        )
        if anchor_m:
            anchor = anchor_m.start()
            window_start = max(0, anchor - 3000)
            before = html[window_start:anchor]
            price_matches = re.findall(r'"price":\{"customerPrice":([0-9.]+)', before)
            if price_matches:
                price = float(price_matches[-1])

            after = html[anchor:anchor + 1200]
            m = re.search(r'"buttonState":"[A-Z_]+","condition":"NEW","displayText":"([^"]+)"', after)
            if m:
                availability = m.group(1).strip()

    rating = None
    m = re.search(r'"reviewInfo":\{"averageRating":([0-9.]+),"reviewCount":(\d+)', html)
    if m:
        rating = {"value": float(m.group(1)), "count": int(m.group(2))}

    reason = None if (name and price is not None and availability and rating) else "partial_data_missing (no product-schema block; parsed from inline GraphQL payload)"
    return {"name": name, "price": price, "availability": availability, "rating": rating, "reason": reason}


def parse_bestbuy(html, url=None):
    block = detect_bot_block(html)
    if block:
        return empty_result(f"blocked_by_bot_protection ({block})")

    m = re.search(r'<script[^>]*id="product-schema"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        m = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(\s*\{[^<]*"@type"\s*:\s*"Product".*?)</script>', html, re.S)
    if not m:
        return _parse_bestbuy_from_graphql_blob(html, url)

    try:
        data = json.loads(m.group(1))
    except Exception as e:
        return empty_result(f"json_parse_error: {e}")

    name = data.get("name")
    rating = None
    agg = data.get("aggregateRating") or {}
    if agg.get("ratingValue") is not None:
        rating = {"value": agg.get("ratingValue"), "count": agg.get("reviewCount")}

    price = None
    availability = None
    offers = data.get("offers")
    if isinstance(offers, list) and offers:
        offer = offers[0]
    elif isinstance(offers, dict):
        offer = offers
    else:
        offer = {}
    if offer.get("price") is not None:
        price = float(offer["price"])
    avail_url = offer.get("availability", "")
    if avail_url:
        availability = avail_url.rsplit("/", 1)[-1]
        availability = re.sub(r"(?<!^)(?=[A-Z])", " ", availability).strip()

    reason = None if (name and price is not None and availability and rating) else "partial_data_missing"
    return {"name": name, "price": price, "availability": availability, "rating": rating, "reason": reason}


# --------------------------------------------------------------------------
# Walmart: __NEXT_DATA__ JSON blob embedded in the page.
# --------------------------------------------------------------------------
def parse_walmart(html):
    block = detect_bot_block(html)
    if block:
        return empty_result(f"blocked_by_bot_protection ({block})")

    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return empty_result("next_data_not_found")

    try:
        data = json.loads(m.group(1))
    except Exception as e:
        return empty_result(f"json_parse_error: {e}")

    try:
        product = data["props"]["pageProps"]["initialData"]["data"]["product"]
    except Exception:
        return empty_result("product_node_not_found")

    if not product:
        return empty_result("product_node_empty")

    name = product.get("name")
    price = None
    price_info = (product.get("priceInfo") or {}).get("currentPrice") or {}
    if price_info.get("price") is not None:
        price = float(price_info["price"])

    availability = product.get("availabilityStatus")
    if availability:
        availability = availability.replace("_", " ").title()

    rating = None
    if product.get("averageRating") is not None:
        rating = {"value": product.get("averageRating"), "count": product.get("numberOfReviews")}

    reason = None if (name and price is not None and availability and rating) else "partial_data_missing"
    return {"name": name, "price": price, "availability": availability, "rating": rating, "reason": reason}


# --------------------------------------------------------------------------
# Amazon: static/rendered HTML, values pulled from well-known element ids.
# --------------------------------------------------------------------------
def parse_amazon(html):
    block = detect_bot_block(html)
    if block:
        return empty_result(f"blocked_by_bot_protection ({block})")

    if re.search(r'id="captchacharacters"', html):
        return empty_result("blocked_by_bot_protection (captcha)")

    m = re.search(r'id="productTitle"[^>]*>\s*([^<]+?)\s*<', html)
    name = m.group(1).strip() if m else None

    price = None
    for pat in [
        r'id="corePriceDisplay_desktop_div"[\s\S]{0,600}?a-offscreen">\$([0-9,.]+)</span>',
        r'id="corePrice_feature_div"[\s\S]{0,600}?a-offscreen">\$([0-9,.]+)</span>',
        r'id="unifiedPrice_feature_div"[\s\S]{0,600}?a-offscreen">\$([0-9,.]+)</span>',
        r'id="priceblock_ourprice">\$([0-9,.]+)<',
        r'id="priceblock_dealprice">\$([0-9,.]+)<',
    ]:
        m = re.search(pat, html)
        if m:
            price = float(m.group(1).replace(",", ""))
            break

    availability = None
    m = re.search(r'class="[^"]*availability-message[^"]*"[^>]*>\s*([^<]+?)\s*<', html)
    if m and m.group(1).strip():
        availability = m.group(1).strip()
    elif re.search(r'id="availability"[\s\S]{0,300}?Currently unavailable', html):
        availability = "Currently unavailable"

    rating = None
    m = re.search(r'id="acrPopover"[^>]*title="([0-9.]+) out of 5 stars"', html)
    if not m:
        m = re.search(r'"ratingValue"\s*:\s*"?([0-9.]+)"?', html)
    if m:
        value = float(m.group(1))
        count = None
        cm = re.search(r'id="acrCustomerReviewText"[^>]*aria-label="([0-9,]+)\s+Reviews"', html)
        if not cm:
            cm = re.search(r'id="acrCustomerReviewText"[^>]*>\(?([0-9,]+)\)?', html)
        if cm:
            count = int(cm.group(1).replace(",", ""))
        rating = {"value": value, "count": count}

    if availability and "cannot be shipped to your selected delivery location" in availability.lower():
        reason = "no_price_shown (item not offered for shipping to this network's detected region)"
    elif availability and "unavailable" in availability.lower() and price is None:
        reason = "no_price_shown (listing marked unavailable)"
    elif price is None and availability is None and name and rating:
        reason = "no_offer_shown (amazon buy-box not present for this item/region)"
    else:
        reason = None if (name and price is not None and availability and rating) else "partial_data_missing"
    return {"name": name, "price": price, "availability": availability, "rating": rating, "reason": reason}


# --------------------------------------------------------------------------
# Target: price is injected client-side, so this expects browser-rendered
# HTML (see fetch.py). Falls back gracefully if only static HTML is given.
# --------------------------------------------------------------------------
def parse_target(html):
    block = detect_bot_block(html)
    if block:
        return empty_result(f"blocked_by_bot_protection ({block})")

    m = re.search(r'<h1[^>]*data-test="product-title"[^>]*>([^<]+)<', html)
    if not m:
        m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    name = m.group(1).strip() if m else None

    price = None
    m = re.search(r'data-test="product-price"[^>]*>\$([0-9,.]+)<', html)
    if m:
        price = float(m.group(1).replace(",", ""))

    rating = None
    m = re.search(r'Average customer rating is ([0-9.]+) out of 5 stars with ([0-9,]+) reviews', html)
    if m:
        rating = {"value": float(m.group(1)), "count": int(m.group(2).replace(",", ""))}

    availability = None
    low = html.lower()
    if "add to cart" in low and "sold out" not in low:
        availability = "In Stock"
    elif "sold out" in low or "out of stock" in low:
        availability = "Out of Stock"
    elif "preorder" in low:
        availability = "Preorder"

    reason = None if (name and price is not None and availability and rating) else "partial_data_missing (target price/availability require JS rendering)"
    return {"name": name, "price": price, "availability": availability, "rating": rating, "reason": reason}


# --------------------------------------------------------------------------
# Newegg: price-current widget + product-inventory availability block.
# --------------------------------------------------------------------------
def parse_newegg(html):
    block = detect_bot_block(html)
    if block:
        return empty_result(f"blocked_by_bot_protection ({block})")

    m = re.search(r'<h1[^>]*class="product-title"[^>]*>([^<]+)<', html)
    if not m:
        m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    name = m.group(1).strip() if m else None

    price = None
    m = re.search(r'class="price-current"[\s\S]{0,200}?<strong>([0-9,]+)</strong>\s*<sup>(\.[0-9]+)</sup>', html)
    if m:
        price = float(m.group(1).replace(",", "") + m.group(2))

    availability = None
    m = re.search(r'class="product-inventory"[\s\S]{0,200}?<strong>([^<]+)</strong>', html)
    if m:
        availability = m.group(1).strip().title()

    rating = None
    m = re.search(r'class="rating"[^>]*title="([^"]+)"', html)
    if m:
        rm = re.search(r'([0-9.]+)', m.group(1))
        if rm:
            count = None
            cm = re.search(r'class="item-rating-num"[^>]*>\(?([0-9,]+)\)?', html)
            if cm:
                count = int(cm.group(1).replace(",", ""))
            rating = {"value": float(rm.group(1)), "count": count}

    reason = None if (name and price is not None and availability and rating) else "partial_data_missing"
    return {"name": name, "price": price, "availability": availability, "rating": rating, "reason": reason}


PARSERS = {
    "bestbuy": parse_bestbuy,
    "walmart": parse_walmart,
    "amazon": parse_amazon,
    "target": parse_target,
    "newegg": parse_newegg,
}


def parse(retailer, html, url=None):
    parser = PARSERS.get(retailer)
    if parser is None:
        return empty_result(f"no_parser_for_retailer:{retailer}")
    try:
        if retailer == "bestbuy":
            return parser(html, url)
        return parser(html)
    except Exception as e:
        return empty_result(f"parse_exception: {e}")
