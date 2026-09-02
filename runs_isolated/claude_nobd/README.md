# Competitor Price Tracker

Tracks price, availability, and customer rating for the 10 products / 41
retailer pages listed in `skus.json`, and surfaces new competitor listings
found via web search.

## Rerun everything

```
python3 run.py
```

This single command:

1. Re-fetches all 41 product pages from `skus.json` (unchanged — never modified
   by this tool) using the `bdata` CLI (Bright Data):
   - Amazon, Walmart, Best Buy → structured pipelines (`bdata pipelines
     amazon_product|walmart_product|bestbuy_products`).
   - Target, Newegg → `bdata scrape --format markdown --zone web_unlocker`,
     parsed with regex (Target requires the `web_unlocker` zone to bypass the
     Premium-domain restriction on the default zone).
   - Raw responses are saved under `raw/`.
2. Writes `results.json` — one row per (product, retailer) page with
   `sku_id, product, retailer, url, name, price, availability, rating, status`.
   `status` is `"ok"` when the page was read successfully; otherwise a short
   reason string, and the unavailable fields are `null`.
3. Runs a web search per product (`bdata search`) and writes
   `new_listings.json` — up to 5 additional retailer URLs per product not
   already present in `skus.json`.

Public pages only — no login, no credentials, no scraping behind auth walls.

## View the dashboard

`dashboard.html` is self-contained and loads `results.json` at runtime, so it
always reflects the latest run without being rebuilt. Some browsers block
`fetch()` against local files opened directly (`file://`), so serve the folder:

```
python3 -m http.server 8000
```

then open `http://localhost:8000/dashboard.html`. It shows every product with
its price at each retailer, highlights the cheapest retailer per product, and
lets you filter by product name or hide out-of-stock cells.

## Files

| File | Description |
|---|---|
| `skus.json` | Input — 10 products × retailer URLs. Never modified. |
| `run.py` | Single-command pipeline: fetch → parse → `results.json` + `new_listings.json`. |
| `results.json` | Latest scrape results, one row per page. |
| `new_listings.json` | Up to 5 new competitor URLs per product, from web search. |
| `dashboard.html` | Self-contained price-comparison table, reads `results.json`. |
| `raw/` | Raw pipeline/scrape output per page, for debugging. |
| `search/` | Raw search results used to build `new_listings.json`. |

## Notes / known limitations

- Best Buy's structured pipeline occasionally returns a transient crawler
  error (HTTP/2 navigation failure); `run.py` retries each page up to twice
  before recording `status: "fetch error: ..."`.
- Newegg rarely surfaces a star rating on its product pages even when in
  stock — `rating` is legitimately `null` in that case, not a fetch failure.
- Retailer catalogs drift over time (e.g. a SKU listed as "Pro 2" may now
  redirect to a newer "Pro 3" listing); `name` reflects whatever the page
  currently shows.
