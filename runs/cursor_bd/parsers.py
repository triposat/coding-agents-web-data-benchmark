"""Extract product fields from scraped markdown by retailer."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


PRICE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)")
RATING_RE = re.compile(
    r"(\d(?:\.\d)?)\s*(?:out of 5 stars?|/ ?5|stars?)",
    re.IGNORECASE,
)


def detect_retailer(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "amazon." in host:
        return "amazon"
    if "bestbuy." in host:
        return "bestbuy"
    if "walmart." in host:
        return "walmart"
    if "target." in host:
        return "target"
    if "newegg." in host:
        return "newegg"
    return "other"


def _first_price(text: str, *, skip_below: float = 5.0) -> str | None:
    for match in PRICE_RE.finditer(text):
        value = float(match.group(1).replace(",", ""))
        if value >= skip_below:
            return f"${value:,.2f}"
    return None


def _first_rating(text: str) -> str | None:
    match = RATING_RE.search(text)
    if match:
        return match.group(1)
    bracket = re.search(r"\[(\d\.\d)\s+\d", text)
    if bracket:
        return bracket.group(1)
    return None


def parse_amazon(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {"name": None, "price": None, "availability": None, "rating": None}
    if not text or len(text) < 200:
        return fields

    title_match = re.search(r"Amazon\.com:\s*(.+?)\s*:\s*", text)
    if title_match:
        fields["name"] = title_match.group(1).strip()
    else:
        h1 = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if h1:
            fields["name"] = h1.group(1).strip()

    # Price near buybox — prefer embedded buybox JSON, then explicit Price label
    buybox = text[:20000]
    json_price = re.search(r'"displayPrice"\s*:\s*"(\$[\d,]+(?:\.\d{2})?)"', buybox)
    if json_price:
        fields["price"] = json_price.group(1)
    else:
        price_match = re.search(
            r"Price\s*\(\$([\d,]+(?:\.\d{2})?)",
            buybox,
            re.IGNORECASE,
        )
        if price_match:
            fields["price"] = f"${float(price_match.group(1).replace(',', '')):,.2f}"
        else:
            prices = [
                float(m.group(1).replace(",", ""))
                for m in PRICE_RE.finditer(buybox[:8000])
                if float(m.group(1).replace(",", "")) >= 20
            ]
            if prices:
                fields["price"] = f"${prices[0]:,.2f}"

    avail_section = buybox[:10000]
    if re.search(r"\bIn Stock\b", avail_section, re.IGNORECASE):
        fields["availability"] = "In Stock"
    elif re.search(
        r"Currently unavailable|Out of Stock|Temporarily out of stock",
        avail_section,
        re.IGNORECASE,
    ):
        fields["availability"] = "Out of Stock"
    elif re.search(r"Only \d+ left", avail_section, re.IGNORECASE):
        fields["availability"] = "Limited Stock"
    elif re.search(r"Add to Cart|Add to cart", avail_section):
        fields["availability"] = "In Stock"

    rating_match = re.search(
        r"(\d\.\d)\s+out of 5 stars(?:\s+\(?([\d,]+)\)?)?",
        text[:15000],
        re.IGNORECASE,
    )
    if rating_match:
        fields["rating"] = rating_match.group(1)
    else:
        fields["rating"] = _first_rating(text[:15000])

    return fields


def parse_bestbuy(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {"name": None, "price": None, "availability": None, "rating": None}
    if not text or len(text) < 100:
        return fields

    title = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if title:
        fields["name"] = title.group(1).strip()
    else:
        t = re.search(r"^(.+?)\s*[-–|]\s*Best Buy", text, re.MULTILINE)
        if t:
            fields["name"] = t.group(1).strip()

    price_match = re.search(
        r"(?:current price|your price|sale price|price)[^\n$]{0,40}(\$\d[\d,]*(?:\.\d{2})?)",
        text[:10000],
        re.IGNORECASE,
    )
    if price_match:
        fields["price"] = price_match.group(1)
    else:
        fields["price"] = _first_price(text[:8000])

    if re.search(
        r"Add to Cart|Pick up today|Shipping available|Get it by|Sold Out\?",
        text[:8000],
        re.IGNORECASE,
    ):
        if re.search(r"Sold Out|Unavailable|Coming Soon", text[:8000], re.IGNORECASE):
            fields["availability"] = "Out of Stock"
        else:
            fields["availability"] = "In Stock"
    elif re.search(r"Sold Out|Unavailable|Coming Soon", text[:8000], re.IGNORECASE):
        fields["availability"] = "Out of Stock"

    rating_match = re.search(r"(\d\.\d)\s*(?:out of 5|stars)", text[:12000], re.IGNORECASE)
    if rating_match:
        fields["rating"] = rating_match.group(1)
    else:
        fields["rating"] = _first_rating(text[:12000])

    return fields


def parse_walmart(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {"name": None, "price": None, "availability": None, "rating": None}
    if not text or len(text) < 100:
        return fields

    title = re.search(r"^(.+?)\s*[-–]\s*Walmart\.com", text, re.MULTILINE)
    if title:
        fields["name"] = title.group(1).strip()
    else:
        h1 = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if h1:
            fields["name"] = h1.group(1).strip()

    section = text[:10000]
    now_match = re.search(r"Now\s*\$([\d,]+(?:\.\d{2})?)", section, re.IGNORECASE)
    if now_match:
        fields["price"] = f"${float(now_match.group(1).replace(',', '')):,.2f}"
    else:
        fields["price"] = _first_price(section)

    rating_match = re.search(r"(\d\.\d)\s+out of 5 stars", section, re.IGNORECASE)
    if rating_match:
        fields["rating"] = rating_match.group(1)
    else:
        stars = re.search(r"(\d\.\d)\s+stars", section, re.IGNORECASE)
        if stars:
            fields["rating"] = stars.group(1)
        else:
            fields["rating"] = _first_rating(section)

    if re.search(r"Add to cart|In stock|Pickup|Shipping", section, re.IGNORECASE):
        fields["availability"] = "In Stock"
    elif re.search(r"Out of stock|Unavailable", section, re.IGNORECASE):
        fields["availability"] = "Out of Stock"

    return fields


def parse_target(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {"name": None, "price": None, "availability": None, "rating": None}
    if not text or len(text) < 100:
        return fields

    h1 = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if h1:
        fields["name"] = h1.group(1).strip()
    else:
        title = re.search(r"^(.+?)\s*:\s*Target", text, re.MULTILINE)
        if title:
            fields["name"] = title.group(1).strip()

    section = text[:8000]
    price_match = re.search(r"\$([\d,]+(?:\.\d{2})?)\s*\n", section)
    if price_match:
        fields["price"] = f"${float(price_match.group(1).replace(',', '')):,.2f}"
    else:
        fields["price"] = _first_price(section)

    if re.search(r"Add to cart|Pickup|Delivery|Shipping", section, re.IGNORECASE):
        fields["availability"] = "In Stock"
    elif re.search(r"Out of stock|Unavailable|Sold out", section, re.IGNORECASE):
        fields["availability"] = "Out of Stock"

    rating_match = re.search(r"(\d+\.\d+)\s+out of 5 stars", section, re.IGNORECASE)
    if rating_match:
        fields["rating"] = rating_match.group(1)
    else:
        fields["rating"] = _first_rating(section)

    return fields


def parse_newegg(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {"name": None, "price": None, "availability": None, "rating": None}
    if not text or len(text) < 100:
        return fields

    h1 = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if h1:
        fields["name"] = h1.group(1).strip()
    else:
        alt = re.search(
            r"!\[Main image of (.+?)\]",
            text[:8000],
            re.IGNORECASE,
        )
        if alt:
            fields["name"] = alt.group(1).strip()

    price_match = re.search(r"\$\s*\*?\*?([\d,]+)\*?\*?\s*\.\s*(\d{2})", text[:6000])
    if price_match:
        fields["price"] = f"${price_match.group(1).replace(',', '')}.{price_match.group(2)}"
    else:
        fields["price"] = _first_price(text[:6000])

    if re.search(r"Add to cart|In Stock|Sold by", text[:6000], re.IGNORECASE):
        fields["availability"] = "In Stock"
    elif re.search(r"OUT OF STOCK|Sold Out|Unavailable", text[:6000], re.IGNORECASE):
        fields["availability"] = "Out of Stock"

    review_match = re.search(r"Reviews\s*\((\d+)\)", text[:8000], re.IGNORECASE)
    if review_match and int(review_match.group(1)) == 0:
        fields["rating"] = None
    else:
        fields["rating"] = _first_rating(text[:8000])

    return fields


def parse_generic(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {"name": None, "price": None, "availability": None, "rating": None}
    if not text:
        return fields
    h1 = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if h1:
        fields["name"] = h1.group(1).strip()
    fields["price"] = _first_price(text[:10000])
    if re.search(r"in stock|add to cart|available", text[:8000], re.IGNORECASE):
        fields["availability"] = "In Stock"
    elif re.search(r"out of stock|unavailable|sold out", text[:8000], re.IGNORECASE):
        fields["availability"] = "Out of Stock"
    fields["rating"] = _first_rating(text[:12000])
    return fields


PARSERS = {
    "amazon": parse_amazon,
    "bestbuy": parse_bestbuy,
    "walmart": parse_walmart,
    "target": parse_target,
    "newegg": parse_newegg,
}


def parse_product(url: str, text: str) -> dict[str, Any]:
    retailer = detect_retailer(url)
    parser = PARSERS.get(retailer, parse_generic)
    return parser(text)


def build_status(fields: dict[str, Any], *, scrape_ok: bool) -> str:
    if not scrape_ok:
        return "scrape failed"
    missing = [k for k in ("name", "price", "availability", "rating") if not fields.get(k)]
    if not missing:
        return "ok"
    if len(missing) == 4:
        return "no data extracted"
    return f"missing: {', '.join(missing)}"
