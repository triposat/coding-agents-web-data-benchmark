# Competitor Price Tracker

Tracks price, availability, and rating for 10 products across 41 retailer
product pages (defined in `skus.json`), through the Bright Data Web Unlocker
MCP server, and renders them in a static dashboard.

## Files

- `skus.json` — frozen list of 10 products x their retailer URLs (41 pages
  total). **Never modified by the tracker.**
- `tracker.py` — the tracker. Scrapes all 41 pages, writes `results.json`,
  then searches the web for additional retailers per product and writes
  `new_listings.json`.
- `results.json` — one row per retailer page: `sku_id`, `product`, `retailer`,
  `url`, `name`, `price`, `availability`, `rating`, `status`. `status` is
  `"ok"` when a product name and price were both read from the page;
  otherwise it's a short reason (`blocked_challenge`, `timeout`,
  `no_price_found`, `rate_limited`, ...) and any field that could not be
  collected is `null`.
- `new_listings.json` — for each of the 10 products, up to 5 additional
  retailer URLs found via web search that are not already in `skus.json`.
- `dashboard.html` — self-contained dashboard (no build step, no external
  requests except loading `results.json`) that tables every product's price
  across retailers and highlights the cheapest one per product.
- `tracker_log.txt` — timestamped run log, overwritten on every run.

## Requirements

- Python 3 (standard library only — no `pip install` needed).
- A working Bright Data MCP endpoint in `.cursor/mcp.json` (or `mcp.json`) in
  this directory, e.g.:

  ```json
  { "mcpServers": { "brightdata": { "type": "http", "url": "https://mcp.brightdata.com/mcp?token=..." } } }
  ```

## Run it

```bash
python3 tracker.py
```

This single command re-scrapes all 41 fixed URLs from `skus.json`, rewrites
`results.json`, then rewrites `new_listings.json`. Re-run it any time to
refresh the data — `dashboard.html` picks up the new `results.json`
automatically on reload.

Notes:
- The Bright Data MCP endpoint has a slow first connection (the handshake can
  take up to ~2 minutes to warm up); after that, individual page fetches
  typically take 3-30 seconds each. A full run over 41 pages + 10 searches
  usually takes well under 30 minutes.
- The script retries a page up to 3 times (with backoff) if the failure looks
  transient (timeout, empty response, rate limit, challenge page).

## View the dashboard

Opening `dashboard.html` directly as a `file://` URL will not work in most
browsers, because they block `fetch()` of local files for security reasons.
Serve the folder instead:

```bash
python3 -m http.server 8000
```

Then open `http://localhost:8000/dashboard.html`.

## Known limitations

- Public retailer pages only; no login or credentials are used anywhere.
- Retailers occasionally serve an anti-bot challenge page or omit one of the
  four fields (e.g. no customer-rating widget on that particular page); those
  rows are recorded with `null` fields and a `status` explaining why, rather
  than being silently dropped.
- `new_listings.json` candidates come from a live web search per product and
  are not themselves verified/scraped — treat them as leads to add to
  `skus.json` after a manual check, not as validated data.
