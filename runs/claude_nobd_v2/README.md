# Competitor Price Tracker

Scrapes 10 products across 41 retailer pages (Amazon, Best Buy, Walmart, Target, Newegg) and produces a live price-comparison dashboard.

## Quick Start

```bash
python3 tracker.py
```

Then open the dashboard:

```bash
python3 -m http.server 8080
# open http://localhost:8080/dashboard.html
```

## What it does

1. **Scrapes** all 41 product pages in `skus.json` and collects:
   - Product name
   - Current price
   - Availability
   - Customer rating

2. **Writes** `results.json` — one record per (product, retailer) pair with keys:
   `sku_id`, `product`, `retailer`, `url`, `name`, `price`, `availability`, `rating`, `status`

3. **Discovers** new retailer listings via web search and writes `new_listings.json`
   (up to 5 additional retailer URLs per product).

4. **Dashboard** — open `dashboard.html` (served via HTTP) to see a filterable, sortable
   price table with the cheapest retailer highlighted per product.

## Requirements

```bash
pip install requests beautifulsoup4 lxml playwright
playwright install chromium
```

## Files

| File | Purpose |
|------|---------|
| `tracker.py` | Main scraper — run this |
| `skus.json` | Input: 10 products × retailer URLs (do not modify) |
| `results.json` | Output: scrape results for all 41 pages |
| `new_listings.json` | Output: additional retailer URLs found via search |
| `dashboard.html` | Self-contained dashboard (loads `results.json` dynamically) |

## Notes

- **Bot protection**: Amazon, Best Buy, and Walmart aggressively block automated
  scraping. Pages from those retailers may return `null` fields with a
  `"blocked: …"` status. Target and Newegg are generally accessible.
- **No credentials used**: only public, unauthenticated pages are accessed.
- **Polite delays**: 1.5 s between requests to avoid hammering servers.
