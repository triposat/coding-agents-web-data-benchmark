# Competitor Price Tracker

Tracks prices for 10 products across 41 retailer product pages listed in `skus.json`.

## Run

```bash
pip install -r requirements.txt && playwright install chromium && python tracker.py
```

This single command:

1. Scrapes all retailer pages in `skus.json`
2. Writes `results.json` with price, availability, and rating data
3. Writes `new_listings.json` with up to 5 additional retailer URLs per product (via web search)

## View dashboard

Open `dashboard.html` in a browser (serve the directory locally if your browser blocks `file://` fetch):

```bash
python -m http.server 8080
```

Then visit http://localhost:8080/dashboard.html

## Output files

| File | Description |
|------|-------------|
| `results.json` | Scraped data for every SKU × retailer combination |
| `new_listings.json` | Additional retailer URLs discovered via search |
| `dashboard.html` | Price comparison table with cheapest retailer highlighted |

## Notes

- Public pages only; no login or credentials required.
- `skus.json` is read-only and never modified.
- Re-run `python tracker.py` anytime to refresh prices.
