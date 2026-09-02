# Competitor Price Tracker

Tracks price, availability, and rating for 10 products across 41 retailer
product pages listed in `skus.json`.

## Files

- `skus.json` — input list of products/retailers/URLs (never modified by a run).
- `results.json` — one row per retailer page: `sku_id, product, retailer, url,
  name, price, availability, rating, status`. `status` is `"ok"` when all
  four fields were collected, otherwise a short reason.
- `new_listings.json` — for each product, up to 5 additional retailer URLs
  (found via web search) selling the same product that aren't in `skus.json`.
- `dashboard.html` — self-contained page that fetches `results.json` and
  shows every product's price at every retailer, with the cheapest retailer
  per product highlighted. Open it via a local server (e.g.
  `python3 -m http.server`, then visit `http://localhost:8000/dashboard.html`)
  since it loads `results.json` with `fetch()`.
- `tracker_prompt.md` — the exact step-by-step procedure the run below follows.

## Re-running the tracker

Product pages are unstructured HTML that differs across five retailers, and
Bright Data's Web Unlocker needs a real extraction step (not brittle
per-site regex) to reliably pull out name/price/availability/rating and to
tell a real block/captcha from a missing field. This repo uses Claude Code
with the Bright Data MCP server (`mcp.json`) to do that extraction, so a
fresh run is a single command:

```
claude --mcp-config mcp.json -p "$(cat tracker_prompt.md)"
```

This re-scrapes all 41 pages, rewrites `results.json` and
`new_listings.json` in place, and never touches `skus.json`.
`dashboard.html` needs no regeneration — it reads whatever is currently in
`results.json`.

Requires Claude Code and a working Bright Data MCP token in `mcp.json`
(public pages only; no login/credentials are used).
