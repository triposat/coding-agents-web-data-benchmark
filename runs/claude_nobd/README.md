# Competitor Price Tracker

Tracks price, availability, and rating for 41 product pages (10 SKUs across
Amazon, Best Buy, Target, Walmart, and Newegg) defined in `skus.json`.

## Files

- `skus.json` — input, list of tracked products/retailers/URLs (never modified by the tracker)
- `track_prices.py` — the tracker; fetches every page and writes the two files below
- `results.json` — one row per (sku, retailer) page: `sku_id`, `product`, `retailer`, `url`, `name`, `price`, `availability`, `rating`, `status`
- `new_listings.json` — up to 5 additional retailer URLs per product found via web search, not already in `skus.json`
- `dashboard.html` — self-contained page that loads `results.json` and shows a price comparison table with the cheapest retailer per product highlighted

## Running it

```
uv run track_prices.py
```

(plain `python3 track_prices.py` also works — the script only uses the standard
library plus the `bdata` CLI). This re-fetches all 41 pages and re-runs the new
listings search, overwriting `results.json` and `new_listings.json`. `skus.json`
is only ever read, never written.

To view the dashboard, open `dashboard.html` in a browser. If your browser blocks
`fetch()` on local files, serve the folder instead:

```
python3 -m http.server 8000
```

then open `http://localhost:8000/dashboard.html`.

## How data is collected

- **Amazon, Best Buy, Walmart** — Bright Data's structured product pipelines
  (`bdata pipelines amazon_product|bestbuy_products|walmart_product <url>`), which
  return clean JSON (name, price, availability, rating) without needing to parse
  HTML.
- **Target, Newegg** — no dedicated structured pipeline exists for these, so the
  script falls back to `bdata scrape <url> --format markdown` and parses price /
  rating / availability / title out of the rendered page with heuristics. This is
  less robust than the structured pipelines above.
- **New listings** — `bdata search "<product> buy" --type shopping`, filtered to
  exclude domains already present in `skus.json` for that product.

## Known limitation

`bdata scrape` and `bdata search` (the Web Unlocker / SERP zones) were returning
`ip_blacklisted` for the account/IP used to build this tracker, so Target/Newegg
scraping and the new-listings search may fail with that status until Bright Data
zone access is restored. The Amazon/Best Buy/Walmart pipelines are unaffected
since they run on Bright Data's own crawling infrastructure rather than this
machine's IP. If you hit `ip_blacklisted` in `status`, check `bdata budget` and
`bdata zones`, or contact Bright Data support about the zone.
