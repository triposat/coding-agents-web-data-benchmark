# Competitor Price Tracker

Tracks prices across 41 retailer product pages listed in `skus.json`, discovers new retailer listings via web search, and displays a comparison dashboard.

## Run

```bash
python3 track.py
```

Requires Python 3.10+ (stdlib only). Bright Data API access is read automatically from `.cursor/mcp.json`, or set `BRIGHTDATA_API_TOKEN`.

## Outputs

| File | Description |
|------|-------------|
| `results.json` | Scraped price, availability, rating, and status for all 41 pages |
| `new_listings.json` | Up to 5 additional retailer URLs per product from web search |
| `dashboard.html` | Price comparison table (open in a browser; serve locally if needed) |

## View dashboard

```bash
python3 -m http.server 8080
```

Then open http://localhost:8080/dashboard.html

## Files

- `track.py` — main entry point
- `brightdata.py` — Bright Data MCP client (scrape + search)
- `parsers.py` — retailer-specific field extraction
- `skus.json` — product catalog (do not modify)
