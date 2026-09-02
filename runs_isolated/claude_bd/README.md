# Competitor Price Tracker

Tracks prices, availability, and ratings for the 10 products / 41 retailer
listings defined in `skus.json`, and surfaces additional competitor listings
found via web search.

## Run it

```
uv run tracker.py
```

This re-fetches every one of the 41 product pages fresh (via the Bright Data
`bdata` CLI web unlocker) and re-runs the competitor search for each of the
10 products. It overwrites `results.json` and `new_listings.json` in place.
`skus.json` is only ever read, never modified.

Requires the `bdata` CLI to be authenticated (`bdata login` or `BRIGHTDATA_API_KEY`
set) with a Web Unlocker zone named `web_unlocker` that has Premium domains
enabled (needed for bestbuy.com and target.com). Check remaining balance first
with `bdata budget` — a full run costs ~51 Bright Data requests (41 scrapes +
10 searches).

## Output files

- **`results.json`** — one entry per product page: `sku_id`, `product`,
  `retailer`, `url`, `name`, `price`, `availability`, `rating`, `status`.
  `status` is `"ok"` when all four fields were collected, otherwise a short
  reason (e.g. `"missing: price, rating"` or `"scrape failed: ..."`).
- **`new_listings.json`** — for each product, up to 5 additional retailer
  URLs (not already in `skus.json`) found via web search.
- **`dashboard.html`** — static page that reads `results.json` and shows a
  price comparison table with the cheapest retailer highlighted per product.
- **`.raw_pages/`** — debug cache of the raw markdown/JSON Bright Data returned
  for each page and search, overwritten every run. Not required for anything;
  useful for inspecting why a given field came back `null`. Safe to delete.

## Viewing the dashboard

Browsers block `fetch()` of local files opened directly as `file://`, so serve
the folder instead:

```
python3 -m http.server 8000
```

then open `http://localhost:8000/dashboard.html`.

## Known data gaps

- Newegg renders its buy-box price and star rating client-side after page
  load, so those two fields are not present in the static scrape and are
  recorded as `null` with a `"missing: ..."` status. Name and availability
  are still collected where present.
- Any page that fails to scrape (removed listing, transient block, etc.) gets
  `status: "scrape failed: <reason>"` with all four fields `null` — rerun the
  tracker to retry.
