import json, re, os

def read(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()

def first_h1(content):
    m = re.search(r'(?m)^# (.+)$', content)
    if m:
        return m.group(1).strip().rstrip('\\*').strip()
    return None

# ---------------------------------------------------------------- AMAZON ----
def extract_amazon(content):
    out = {"product_name": None, "price": None, "availability": None, "rating": None, "notes": []}
    out["product_name"] = first_h1(content)

    anchor_idx = content.find('#averageCustomerReviewsAnchor')
    if anchor_idx != -1:
        window = content[max(0, anchor_idx - 200):anchor_idx + 40]
        m = re.search(r'(\d\.\d) _\1 out of 5 stars_', window)
        if m:
            cnt_m = re.search(r'\((\d[\d,]*)\)\]\(#averageCustomerReviewsAnchor\)', content[anchor_idx - 40:anchor_idx + 40])
            out["rating"] = f"{m.group(1)} out of 5 stars" + (f" ({cnt_m.group(1)} ratings)" if cnt_m else "")
    if out["rating"] is None:
        out["notes"].append("no rating widget found")

    cutoff_idx = content.find('Other sellers on Amazon')
    main_area = content[:cutoff_idx] if cutoff_idx != -1 else content

    unavailable = None
    if re.search(r"Currently unavailable\.?\s*\n\s*We don't know when or if this item will be back in stock", main_area):
        unavailable = "Currently unavailable on Amazon (no restock date given)"
    elif re.search(r'No featured offers available', main_area):
        unavailable = "No featured (Buy Box) offer available on Amazon directly; only third-party listings via 'See All Buying Options'"

    if unavailable:
        out["availability"] = unavailable
        out["notes"].append("price not applicable: no active Amazon offer")
    else:
        cleaned = re.sub(r'\[\s*\$([\d,]+\.\d{2})\s?\$\1\s*\]\(#\)', '', main_area)
        m = re.search(r'\$([\d,]+\.\d{2})\s?\$\1(?!\d)', cleaned)
        if m:
            out["price"] = f"${m.group(1)}"
            tail = cleaned[m.end():m.end() + 800]
            sm = re.search(r'\b(In Stock|Temporarily out of stock|Only \d+ left in stock[^\n]*)\b', tail)
            if sm:
                out["availability"] = sm.group(1)
            else:
                out["notes"].append("stock status text not found near price")
        else:
            out["notes"].append("no price pattern found")
    return out

# --------------------------------------------------------------- WALMART ----
def extract_walmart(content):
    out = {"product_name": None, "price": None, "availability": None, "rating": None, "notes": []}
    out["product_name"] = first_h1(content)

    m = re.search(r'(\d\.\d) out of 5 stars\s*\n+\(\1\)\s*\n+\[?([\d,.]+[KM]?)\+?\s*ratings?\]?', content)
    if m:
        out["rating"] = f"{m.group(1)} out of 5 stars ({m.group(2)} ratings)"
    else:
        out["notes"].append("no rating widget found (likely no reviews yet)")

    m = re.search(r'Current price is USD(?:Now )?\$([\d,]+\.\d{2})', content)
    if m:
        out["price"] = f"${m.group(1)}"
    else:
        out["notes"].append("no price pattern found")

    if re.search(r'\nAdd to cart\n', content):
        out["availability"] = "In stock (Add to cart available)"
    elif re.search(r'Out of stock|Sold out', content, re.I):
        out["availability"] = "Out of stock"
    else:
        out["notes"].append("availability not determined")
    return out

# ---------------------------------------------------------------- TARGET ----
def extract_target(content):
    out = {"product_name": None, "price": None, "availability": None, "rating": None, "notes": []}
    out["product_name"] = first_h1(content)

    m = re.search(r'(\d\.\d{1,2}) out of 5 stars\s*\n+([\d,]+)\s*\n', content)
    if m:
        out["rating"] = f"{m.group(1)} out of 5 stars ({m.group(2)} ratings)"
    else:
        out["notes"].append("no rating widget found")

    price_m = re.search(r'\$([\d,]+\.\d{2}) (?:reg|was) \$([\d,]+\.\d{2})', content)
    if price_m:
        out["price"] = f"${price_m.group(1)} (was ${price_m.group(2)})"
        price_end = price_m.end()
    else:
        price_m = re.search(r'\n\$([\d,]+\.\d{2})\s*\n', content)
        if price_m:
            out["price"] = f"${price_m.group(1)}"
            price_end = price_m.end()
        else:
            out["notes"].append("no price pattern found")
            price_end = None

    if price_end is not None:
        cart_idx = content.find('Add to cart', price_end)
        window_end = cart_idx if cart_idx != -1 else price_end + 400
        window = content[price_end:window_end]
        if re.search(r'Sold out|Out of stock', window, re.I):
            out["availability"] = "Out of stock / Sold out"
        elif cart_idx != -1:
            out["availability"] = "In stock (Add to cart available)"
        else:
            out["notes"].append("availability not determined")
    elif re.search(r'Add to cart', content):
        out["availability"] = "In stock (Add to cart available)"
    return out

# ---------------------------------------------------------------- NEWEGG ----
def extract_newegg(content):
    out = {"product_name": None, "price": None, "availability": None, "rating": None, "notes": []}
    out["product_name"] = first_h1(content)

    for m in re.finditer(r'\$\*\*([\d,]+)\*\*\.(\d{2})(\s*[\u2013-])?', content):
        if m.group(3):
            continue
        out["price"] = f"${m.group(1)}.{m.group(2)}"
        break
    if out["price"] is None:
        out["notes"].append("no price pattern found")

    if re.search(r'OUT OF STOCK|SOLD OUT', content, re.I):
        out["availability"] = "Out of stock"
    elif re.search(r'\nAdd to cart\n', content):
        out["availability"] = "In stock (Add to cart available)"
    else:
        out["notes"].append("availability not determined")

    rc = re.search(r'Reviews \(([\d,]+)\)', content)
    if rc:
        out["notes"].append(f"rating shown only as image icons (eggs), not extractable as text; {rc.group(1)} written reviews listed")
    else:
        out["notes"].append("no reviews section found")
    return out

# --------------------------------------------------------------- BESTBUY ----
def extract_bestbuy(content):
    out = {"product_name": None, "price": None, "availability": None, "rating": None, "notes": []}

    m = re.search(r'\n\n#?\s*([^\n]+?)\s*\n\nModel:', content)
    out["product_name"] = m.group(1).strip() if m else first_h1(content)

    m = re.search(r'Rating (\d\.\d) out of 5 stars with ([\d,]+) reviews', content)
    if m:
        out["rating"] = f"{m.group(1)} out of 5 stars ({m.group(2)} reviews)"
    else:
        out["notes"].append("no rating widget found")

    if re.search(r'no longer available in new condition', content, re.I):
        out["availability"] = "Discontinued - no longer available in new condition (Best Buy)"
        out["notes"].append("no price shown for discontinued listing")
        return out

    price_m = re.search(r'\$([\d,]+\.\d{2})\$[\d,]+(?!\d)', content)
    if price_m:
        out["price"] = f"${price_m.group(1)}"
    else:
        out["notes"].append("no price pattern found")

    if re.search(r'Sold Out|Coming Soon|Currently unavailable', content, re.I):
        out["availability"] = "Sold out / unavailable"
    elif re.search(r'\nAdd to cart\n', content):
        note = ""
        lm = re.search(r'Only (\d+) left', content)
        if lm:
            note = f" (limited stock: only {lm.group(1)} left at nearby store)"
        out["availability"] = f"In stock (Add to cart available){note}"
    elif re.search(r'Only \d+ left|Ready on|Act fast', content):
        out["availability"] = "Likely in stock (limited-stock / pickup-ready signals present); page content was truncated before the Add to Cart button could be confirmed"
    else:
        out["notes"].append("availability not determined")
    return out


DOMAIN_EXTRACTORS = {
    'amazon.com': extract_amazon,
    'walmart.com': extract_walmart,
    'target.com': extract_target,
    'newegg.com': extract_newegg,
    'bestbuy.com': extract_bestbuy,
}

def get_domain(url):
    for d in DOMAIN_EXTRACTORS:
        if d in url:
            return d
    return None

def main():
    with open('skus.json') as f:
        skus = json.load(f)
    with open('url_content_map.json') as f:
        url_map = json.load(f)

    results = []
    for sku in skus:
        sku_id = sku['sku_id']
        product = sku['product']
        for retailer, info in sku['retailers'].items():
            url = info['url']
            row = {
                "sku_id": sku_id,
                "product": product,
                "retailer": retailer,
                "url": url,
                "product_name": None,
                "price": None,
                "availability": None,
                "rating": None,
                "status": None
            }
            entry = url_map.get(url)
            if entry is None:
                row["status"] = "URL not scraped"
                results.append(row)
                continue
            filepath = entry.get('file')
            failed = entry.get('failed', False)
            if failed or not filepath or not os.path.exists(filepath):
                row["status"] = "Scrape failed: source page returned empty/blocked response after repeated retries (likely anti-bot protection or a dropped connection)"
                results.append(row)
                continue
            content = read(filepath)
            if len(content.strip()) == 0:
                row["status"] = "Scrape failed: empty response from source page (possible bot detection)"
                results.append(row)
                continue
            domain = get_domain(url)
            if domain is None:
                row["status"] = "Unknown retailer domain; no extractor available"
                results.append(row)
                continue
            data = DOMAIN_EXTRACTORS[domain](content)
            row["product_name"] = data["product_name"]
            row["price"] = data["price"]
            row["availability"] = data["availability"]
            row["rating"] = data["rating"]
            missing = [k for k in ["product_name", "price", "availability", "rating"] if data.get(k) is None]
            if missing:
                notes = "; ".join(data.get("notes", []))
                row["status"] = f"Partial extraction; missing: {', '.join(missing)}" + (f" ({notes})" if notes else "")
            elif row["availability"] and "truncated" in row["availability"]:
                row["status"] = "OK, but availability is inferred: the scraped page was cut off before the Add to Cart / stock status button"
            else:
                row["status"] = "OK"
            results.append(row)

    with open('results.json', 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Wrote {len(results)} rows to results.json")

if __name__ == '__main__':
    main()
