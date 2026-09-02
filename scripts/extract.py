"""Shared field extraction + outcome classification.
A fetch counts as SUCCESS only if the product NAME and PRICE can both be read.
A 200 that carries a challenge page is BLOCKED, not success."""
import re, json

CHALLENGE = [
    "robot or human", "are you a human", "access denied", "verify you are human",
    "enable javascript and cookies to continue", "unusual traffic", "captcha",
    "request blocked", "pardon our interruption", "bot detection", "just a moment",
    "checking your browser", "attention required",
]
PRICE_RX = [
    re.compile(r'"price"\s*:\s*"?\$?([0-9][0-9,]*\.?[0-9]{0,2})'),
    re.compile(r'itemprop="price"[^>]*content="([0-9][0-9,]*\.?[0-9]{0,2})"'),
    re.compile(r'\$\s?([0-9][0-9,]{0,6}\.[0-9]{2})'),
]
RATING_RX = [
    re.compile(r'"ratingValue"\s*:\s*"?([0-5](?:\.[0-9])?)'),
    re.compile(r'([0-5]\.[0-9])\s*out of\s*5'),
]
AVAIL_JSONLD = re.compile(r'"availability"\s*:\s*"?(?:https?://schema\.org/)?(InStock|OutOfStock|PreOrder|BackOrder|SoldOut)', re.I)
# Markdown and rendered-text surfaces do not carry JSON-LD. Match the human string.
AVAIL_TEXT = [
    (re.compile(r"\bcurrently unavailable\b", re.I), "OutOfStock"),
    (re.compile(r"\bout of stock\b", re.I),          "OutOfStock"),
    (re.compile(r"\bsold out\b", re.I),              "OutOfStock"),
    (re.compile(r"\bpre-?order\b", re.I),            "PreOrder"),
    (re.compile(r"\bback-?order(?:ed)?\b", re.I),    "BackOrder"),
    (re.compile(r"\bin stock\b", re.I),              "InStock"),
    (re.compile(r"\badd to cart\b", re.I),           "InStock"),
    (re.compile(r"\badd to bag\b", re.I),            "InStock"),
]

def availability_of(text):
    m = AVAIL_JSONLD.search(text)
    if m:
        return m.group(1)
    for rx, val in AVAIL_TEXT:      # negative states first, they are more specific
        if rx.search(text):
            return val
    return None

def title_of(html):
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()[:200]
    m = re.search(r"^#\s+(.+)$", html, re.M)      # markdown from BD
    if m:
        return m.group(1).strip()[:200]
    return (html.strip().split("\n", 1)[0][:200] if html.strip() else "")

def first(rxs, text):
    for rx in rxs:
        m = rx.search(text)
        if m:
            return m.group(1)
    return None

def classify(status, body, err=None, is_markdown=False):
    """-> (outcome, fields)"""
    body = body or ""
    low = body.lower()[:600000]
    t = title_of(body)
    tl = t.lower()
    fields = {"name": None, "price": None, "rating": None, "availability": None}
    if err:
        e = err.lower()
        if "timeout" in e:
            return "blocked_timeout", fields
        if "err_http2_protocol_error" in e or "err_connection_reset" in e or "econnreset" in e:
            return "blocked_h2_reset", fields
        return "error", fields
    if status in (403, 429, 503):
        return f"blocked_http_{status}", fields
    if not body.strip():
        return "blocked_empty", fields
    if any(c in tl for c in CHALLENGE):
        return "blocked_challenge", fields
    if any(c in low[:20000] for c in ("px-captcha", "/_Incapsula_Resource", "cf-challenge-running")):
        return "blocked_challenge", fields
    fields["name"] = t or None
    fields["price"] = first(PRICE_RX, body)
    fields["rating"] = first(RATING_RX, body)
    fields["availability"] = availability_of(body)
    if fields["name"] and fields["price"]:
        return "success", fields
    if fields["name"]:
        return "partial_no_price", fields
    return "no_data", fields
