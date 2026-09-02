# Competitor Price Tracker

Tracks price, availability, customer rating and product name across every
retailer product page listed in `skus.json` (10 products, 41 retailer pages:
Amazon, Best Buy, Target, Walmart, Newegg).

## Run it

```bash
python3 scrape.py
```

That single command:

1. Reads `skus.json` (never modified).
2. Visits all 41 product pages and writes `results.json` (one record per
   page, with `sku_id`, `product`, `retailer`, `url`, `name`, `price`,
   `availability`, `rating`, `status`).
3. Runs a web search per product (DuckDuckGo) and writes `new_listings.json`
   with up to 5 additional retailer URLs per product not already present in
   `skus.json`.

Then open `dashboard.html` in a browser (serve the folder over HTTP, since
`fetch()` on a bare `file://` URL is blocked by browsers):

```bash
python3 -m http.server 8000
# then visit http://localhost:8000/dashboard.html
```

## How it works / dependencies

Installed via `pip install requests beautifulsoup4 lxml seleniumbase`
(already present in this environment).

- **Walmart**: plain `requests` GET; the page embeds a `__NEXT_DATA__` JSON
  blob with the full product record (name, price, availability, rating).
  Falls back to a stealth browser if Walmart's bot-detection blocks the
  plain request.
- **Best Buy**: fetched with SeleniumBase's undetected-Chromedriver (`uc=True`)
  mode, since Best Buy's Akamai bot manager silently drops plain HTTP
  clients. Data is parsed from the page's `schema.org/Product` JSON-LD block.
- **Amazon**: fetched the same stealth-browser way; data is scraped from the
  `#productTitle`, buy-box price, `#availability`, and star-rating elements.
  Amazon frequently has no single "featured offer" for a given ASIN (it
  shows "See All Buying Options" or an out-of-stock buy box instead of a
  price) — this is a real Amazon behavior, not a scraping bug, and shows up
  as a `status` explaining the missing price.
- **Target**: stealth browser; data read from `data-test="product-*"`
  attributes (Target intentionally omits price from the server-rendered
  HTML and loads it client-side, so a real browser is required).
- **Newegg**: stealth browser; Newegg shows a "Are you a human?" captcha to
  plain HTTP clients, so data is scraped from the rendered page's
  `.product-title` / `.product-price` / `.product-rating` elements.

Each page fetch is retried up to 3 times if nothing useful was extracted
(these sites occasionally serve an intentionally stripped page to
suspected bots). Any field that still can't be collected after retries is
written as `null`, and `status` is set to a short human-readable reason
instead of `"ok"`.

## Files

- `skus.json` — input, 10 products x retailer URLs (not modified by the tracker).
- `scrape.py` — the tracker script (single entry point).
- `results.json` — output of step 1/2 (41 records).
- `new_listings.json` — output of step 3 (new retailer URLs per product).
- `dashboard.html` — self-contained dashboard; loads `results.json` at
  runtime and shows every product's price at each retailer, highlighting
  the cheapest in-stock retailer per product.

## Notes / limitations

- All targets are public product pages; no login or credentials are used
  anywhere.
- Retailers actively try to block automated access (Akamai on Best Buy,
  PerimeterX on Walmart, captchas on Newegg). SeleniumBase's UC mode gets
  past most of this, but bot-detection is adversarial and can still
  intermittently degrade a given run — re-running `scrape.py` typically
  recovers pages that failed on a prior run.
- `new_listings.json` is produced by a live web search, so its exact
  contents will vary between runs as search results change.
