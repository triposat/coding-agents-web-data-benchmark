# Competitor Price Tracker

Tracks current price, availability, customer rating, and product name for
every retailer product page listed in `skus.json` (10 products x up to 5
retailers each = 41 pages), and discovers additional retailer listings via
public web search.

## One-time setup

```bash
pip install -r requirements.txt
python3 -m patchright install chromium
```

(`patchright` is a detection-hardened fork of Playwright, used only to
render the handful of retailer pages whose price is injected client-side
after page load. `python3 -m patchright install chromium` downloads the
headless browser binary; skip it if you already have Playwright's Chromium
installed.)

## Running the tracker (single command)

```bash
bash scripts/run_all.sh
```

This re-fetches all 41 pages from `skus.json` (never modifying that file)
and writes/overwrites:

- `results.json` — one row per (product, retailer) pair with
  `sku_id, product, retailer, url, name, price, availability, rating, status`.
  `status` is `"ok"` when all four fields were collected, otherwise a short
  reason string (e.g. a bot-protection block, or a region/stock restriction
  reported by the retailer itself).
- `new_listings.json` — for each of the 10 products, up to 5 additional
  retailer URLs (found via a public DuckDuckGo search) that are not already
  in `skus.json`.

You can also run either step independently:

```bash
python3 scripts/scrape.py          # results.json only
python3 scripts/new_listings.py    # new_listings.json only
```

## Viewing the dashboard

`dashboard.html` is a self-contained page that loads `results.json` and
shows, per product, every retailer's price/availability/rating with the
cheapest retailer highlighted. Because it uses `fetch()` to load a local
JSON file, most browsers require it to be served over HTTP rather than
opened directly as a `file://` URL:

```bash
python3 -m http.server 8000
# then open http://localhost:8000/dashboard.html
```

## How it works / design notes

- **Best Buy** and **Walmart**: fetched with `curl_cffi` (Chrome TLS
  fingerprint impersonation, no JS needed). Best Buy exposes a
  `schema.org/Product` JSON-LD block; Walmart embeds a Next.js
  `__NEXT_DATA__` JSON blob. Both are parsed directly.
- **Amazon**: fetched the same way, with a public, unauthenticated
  "ship to United States / USD" cookie pair set (the same choice a human
  visitor can make from Amazon's own country/currency selector — no login
  or credentials involved). Even so, Amazon does not always show a
  price/buy-box for every ASIN to every network: some listings are
  region-shipping-restricted or marked unavailable. When that happens the
  page is still parsed for whatever *is* present (name, rating,
  availability message) and `status` explains what's missing and why.
- **Target**: Target only injects price into the DOM via a client-side
  API call after the page loads, so these pages are rendered with a
  headless browser (`patchright`) and then parsed.
- **Newegg**: presents an interactive "Are you a human?" challenge to
  automated traffic (observed with both plain HTTP and full headless-Chrome
  fetches). The tracker still attempts every Newegg page on every run — no
  results are hardcoded — but expect these to come back with
  `status: "blocked_by_bot_protection..."` unless run from a network Newegg
  trusts.
- Every fetch strategy is retailer-driven and generic (no per-SKU special
  casing), so re-running the tracker against the same `skus.json` targets
  is deterministic in approach, even if individual sites' bot-defenses or
  regional offers change what comes back.

## Files

| File | Description |
|---|---|
| `skus.json` | Input: 10 products x retailer product-page URLs. Read-only, never modified. |
| `results.json` | Output of `scripts/scrape.py`. |
| `new_listings.json` | Output of `scripts/new_listings.py`. |
| `dashboard.html` | Self-contained viewer for `results.json`. |
| `scripts/parsers.py` | Per-retailer HTML/JSON field extraction. |
| `scripts/fetch.py` | HTTP (`curl_cffi`) + headless-browser (`patchright`) fetch helpers. |
| `scripts/scrape.py` | Orchestrates fetching + parsing all 41 pages into `results.json`. |
| `scripts/new_listings.py` | Public web search for additional retailer listings per product. |
| `scripts/run_all.sh` | Single-command entry point (runs both scripts above). |

## Last run result

Fully collected all 4 fields (`status: "ok"`) for **28 of the 41** product
pages. See `results.json` for the per-page `status` explaining the other 13
(mostly Newegg's bot-challenge and a handful of Amazon listings that are
region-restricted or marked unavailable on this network).
