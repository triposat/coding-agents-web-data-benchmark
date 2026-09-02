#!/usr/bin/env python3
"""Assemble results.json from raw/ pipeline outputs + manual target/newegg data."""
import json
import re
import os

BASE = os.path.dirname(os.path.abspath(__file__))


def load(path):
    with open(path) as f:
        return json.load(f)


def to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"[\d,]+\.?\d*", v.replace(",", ""))
        if m:
            try:
                return float(m.group())
            except ValueError:
                return None
    return None


def parse_amazon(d):
    name = d.get("title")
    price = to_float(d.get("final_price") if d.get("final_price") is not None else d.get("price"))
    availability = d.get("availability")
    if availability is None and d.get("is_available") is not None:
        availability = "In Stock" if d["is_available"] else "Out of Stock"
    rating = d.get("rating")
    return name, price, availability, rating


def parse_walmart(d):
    name = d.get("product_name")
    price = to_float(d.get("final_price") if d.get("final_price") is not None else d.get("price"))
    availability = d.get("availability")
    if not availability:
        availability = "in_stock" if d.get("is_available") else "out_of_stock"
    rating = d.get("rating")
    return name, price, availability, rating


def parse_bestbuy(d):
    name = d.get("title")
    price = to_float(d.get("final_price") if d.get("final_price") is not None else d.get("price"))
    availability = d.get("availability_new") or d.get("availability")
    if isinstance(availability, list):
        availability = ", ".join(
            a.get("availability_name", "") for a in availability if isinstance(a, dict)
        ) or None
    rating = d.get("rating")
    return name, price, availability, rating


PARSERS = {"amazon": parse_amazon, "walmart": parse_walmart, "bestbuy": parse_bestbuy}


def main():
    skus = load(os.path.join(BASE, "skus.json"))
    manual = load(os.path.join(BASE, "raw", "manual_target_newegg.json"))

    results = []
    missing_pipeline = []

    for s in skus:
        sku_id = s["sku_id"]
        product = s["product"]
        for retailer, info in s["retailers"].items():
            url = info["url"]
            key = f"{sku_id}_{retailer}"
            entry = {
                "sku_id": sku_id,
                "product": product,
                "retailer": retailer,
                "url": url,
                "name": None,
                "price": None,
                "availability": None,
                "rating": None,
                "status": None,
            }

            if retailer in ("target", "newegg"):
                m = manual.get(key)
                if m:
                    entry["name"] = m.get("name")
                    entry["price"] = m.get("price")
                    entry["availability"] = m.get("availability")
                    entry["rating"] = m.get("rating")
                    entry["status"] = "ok"
                else:
                    entry["status"] = "not collected"
            else:
                raw_path = os.path.join(BASE, "raw", f"{key}.json")
                if not os.path.exists(raw_path):
                    entry["status"] = "pending fetch"
                    missing_pipeline.append(key)
                else:
                    try:
                        data = load(raw_path)
                        if isinstance(data, list):
                            if not data:
                                entry["status"] = "no data returned"
                                results.append(entry)
                                continue
                            data = data[0]
                        if not isinstance(data, dict) or "error" in data:
                            entry["status"] = f"fetch error: {data.get('error') if isinstance(data, dict) else 'unknown'}"
                            results.append(entry)
                            continue
                        name, price, availability, rating = PARSERS[retailer](data)
                        entry["name"] = name
                        entry["price"] = price
                        entry["availability"] = availability
                        entry["rating"] = rating
                        entry["status"] = "ok"
                    except Exception as e:
                        entry["status"] = f"parse error: {e}"

            results.append(entry)

    out_path = os.path.join(BASE, "results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    total = len(results)
    complete = sum(
        1
        for r in results
        if r["name"] is not None
        and r["price"] is not None
        and r["availability"] is not None
        and r["rating"] is not None
    )
    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"Wrote {total} entries to results.json")
    print(f"Status=ok: {ok}/{total}")
    print(f"All four fields present: {complete}/{total}")
    if missing_pipeline:
        print(f"Still pending pipeline fetch: {missing_pipeline}")


if __name__ == "__main__":
    main()
