# Competitor price tracker

Tracks price, availability, and rating for the 10 products / 41 retailer
pages listed in `skus.json` (never modified by this tool), across Best Buy,
Amazon, Walmart, Target, and Newegg.

## Rerun it

```
python3 tracker.py
```

That's the one command. It re-reads `skus.json`, re-fetches every one of the
41 pages, and overwrites `results.json`. Nothing else needs to run first.

Setup (one-time):

```
pip install -r requirements.txt
```

### Auth

Fetching goes through the [Bright Data Web Unlocker](https://docs.brightdata.com/scraping-automation/web-unlocker/introduction)
API, which defeats the basic bot-detection most of these retail sites use on
their public product pages (no login, no account, no retailer credentials
involved anywhere — this is strictly a scraping-proxy credential for reaching
public pages). It needs:

- `BRIGHTDATA_API_KEY` — a Bright Data API key/token.
- `BRIGHTDATA_ZONE` — a Web Unlocker zone name on that account (defaults to
  `web_unlocker`).

If `BRIGHTDATA_API_KEY` isn't set, the script falls back to reading the token
out of `mcp.json`'s `?token=...` query string, which is already present in
this folder — convenient for this environment, but set the env var yourself
if you move this project or the MCP config goes away.

## Files

- `skus.json` — input, 10 products × their retailer URLs. Read-only.
- `tracker.py` — the tracker. Fetches all 41 pages (6 at a time, with retries
  for the unlocker's occasional empty-response flakiness), parses out
  product name / price / availability / rating per retailer, writes
  `results.json`. Raw responses are cached under `cache/` for debugging.
- `results.json` — output, one JSON object per retailer page with keys
  `sku_id`, `product`, `retailer`, `url`, `name`, `price`, `availability`,
  `rating`, `status`. `status` is `"ok"` when all four fields were collected,
  otherwise a short reason (e.g. `missing_availability`, `empty_response`).
- `new_listings.json` — for each of the 10 products, up to 5 extra retailer
  URLs (not in `skus.json`) found via web search, e.g. B&H Photo, Micro
  Center, Costco, eBay, Adorama, Staples. This is a point-in-time research
  snapshot (built with a web search, not re-run by `tracker.py`); rebuild it
  by re-running the same search queries if you want a refresh.
- `dashboard.html` — single self-contained HTML file (no build step, no
  external requests besides loading the two JSON files above). Open it to
  see a table of every product with its price at each retailer, with the
  cheapest retailer per product highlighted in green. Also renders the
  `new_listings.json` suggestions underneath if that file is present.

## Viewing the dashboard

Browsers block `fetch()` of local JSON files when an HTML file is opened
directly from disk (`file://...`). Serve the folder instead:

```
python3 -m http.server 8000
```

then open `http://localhost:8000/dashboard.html`.

## Known limitations

- A handful of pages genuinely don't expose all four fields in server-side
  HTML (e.g. a BestBuy PDP template that loads price via a client-side call,
  or an Amazon listing with no current offer/buy box). These are recorded
  with `price`/`availability` as `null` and a `status` explaining why, rather
  than guessed.
- Target price/rating come from Target's own public `redsky` product API
  (the same one its website calls, using the same public key it ships to
  every visitor); availability comes from a second call to Target's
  fulfillment API using a fixed store id/ZIP (New York, NY) as a stand-in
  "your location" — availability elsewhere may vary slightly.
