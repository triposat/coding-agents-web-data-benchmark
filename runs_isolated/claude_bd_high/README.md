# Competitor Price Tracker

Tracks price, availability, and rating for 10 products across 41 retailer
product pages (Amazon, Best Buy, Walmart, Target, Newegg), sourced from
`skus.json`.

## Files

| File | What it is |
|---|---|
| `skus.json` | Input — 10 products, each with retailer URLs. **Never modified.** |
| `scraped_content.json` | Raw scraped markdown/text for each of the 41 URLs (`{url, content}`). Regenerated on every rerun. |
| `extract.py` | Pure text-processing: turns `scraped_content.json` into `results.json` using per-retailer regex extractors. No network access. |
| `results.json` | Output — one row per (product, retailer): `sku_id, product, retailer, url, name, price, availability, rating, status`. |
| `new_listings.json` | Output — up to 5 additional retailer URLs per product not already in `skus.json`, found via web search. |
| `dashboard.html` | Self-contained dashboard. Loads `results.json` at page-load time and renders one table per product, highlighting the cheapest in-stock retailer. |
| `rerun_prompt.md` | Instructions handed to Claude Code to redo the scrape + extraction + web search. |
| `rerun.sh` | The single rerun command (see below). |

## Rerunning the tracker

```
./rerun.sh
```

This regenerates `scraped_content.json`, `results.json`, and
`new_listings.json`. `dashboard.html` doesn't need to change between runs —
it just reads whatever `results.json` currently contains.

### Why this isn't a plain standalone script

Getting past bot protection on bestbuy.com/amazon.com/target.com from this
sandbox requires Bright Data's unlocker, which is only reachable here through
the Bright Data **MCP server** (`mcp.json`) — there's no separate Bright Data
REST API key/zone configured in this environment. So `rerun.sh` runs Claude
Code itself, non-interactively (`claude -p`), with that MCP server attached
and `rerun_prompt.md` as the prompt. Claude does the scraping (with retries
for bot-blocked pages) and the web search for new listings, then shells out to
`python3 extract.py` — the only part of the pipeline that's a plain,
deterministic script — to turn raw page content into `results.json`.

Requires the `claude` CLI to be installed and already authenticated, and
`mcp.json` (with a valid Bright Data MCP token) to be present in this
directory.

## Viewing the dashboard

`dashboard.html` fetches `results.json` with `fetch()`, which browsers block
against `file://` URLs. Serve the directory over HTTP instead:

```
python3 -m http.server 8000
```

then open `http://localhost:8000/dashboard.html`.

## Known, permanent data gaps

Out of 41 pages, **30 have all four fields** (name, price, availability,
rating) fully collected. The 11 that don't, and why:

- **1 page (Bose QuietComfort Ultra, Best Buy)** — never returned content
  after 9 retries; Best Buy's bot protection blocked it outright this run.
- **2 Best Buy pages (Sony WH-1000XM5, Razer DeathAdder V3)** — the pages
  loaded fine but say "This item is no longer available in new condition."
  `price: null` here is a correct reflection of the page, not a scraping
  failure.
- **2 Amazon pages (AirPods Pro 2, SanDisk Extreme)** — the buybox failed to
  render (page shows a "session has expired" placeholder instead of price).
  Retried twice; no reliable price signal in either. One page happened to
  have a same-brand comparison table with a price string in it, but it
  belonged to a *different* AirPods model, so it was deliberately **not**
  used — a wrong price is worse than a missing one.
- **5 Newegg pages** — the star rating is rendered as an image sprite with no
  text/JSON-LD equivalent anywhere in the scraped markdown. This is a
  structural limitation of scraping Newegg's markdown, not a bug in
  `extract.py`.

These are inherent to what's visible in the page content at scrape time (bot
blocking, discontinued listings, transient render failures, sprite-based
ratings), not extraction bugs — a rerun may recover some of them (e.g. if
Best Buy's protection doesn't trigger that day) and could just as easily hit
new ones elsewhere, since these retailers' bot detection is non-deterministic.
