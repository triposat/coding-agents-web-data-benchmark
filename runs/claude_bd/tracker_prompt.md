# Competitor price tracker — refresh instructions

Run this entire procedure in one sitting. Do not modify `skus.json`.

## 1. Collect the 41 product pages

Read `skus.json`. It lists 10 products (`sku_id`, `product`) each with a
`retailers` map of `retailer name -> {url}`. Flatten this into exactly 41
`(sku_id, product, retailer, url)` targets.

For every target, in parallel batches of ~8-10:
- Scrape the `url` with the `mcp__brightdata__scrape_as_markdown` MCP tool
  (server configured in `mcp.json` in this directory).
- From the returned content, extract:
  - `name`: the full product title as shown on the page
  - `price`: the current selling price as a plain number (no currency symbol)
  - `availability`: the stock/availability status text as shown on the page
    (e.g. "In Stock", "Out of Stock", "Only 1 left in stock")
  - `rating`: the customer star rating as a plain number out of 5 (null if
    the page genuinely shows no rating)
- Set `status` to `"ok"` only when all four of `name`, `price`,
  `availability`, and `rating` were captured (non-null). If any field is
  missing, set `status` to a short lowercase reason (e.g. `"blocked"`,
  `"captcha"`, `"page not found"`, `"rating not shown on page"`,
  `"price not shown on page"`). Do not guess values — use `null` for
  anything you could not read off the page.
- If the scrape itself fails, is blocked, or returns a captcha/error page,
  set all four fields to `null` and `status` to a short reason (e.g.
  `"blocked"`).

Public pages only — never log in or use credentials.

## 2. Write results.json

Write a JSON array to `results.json` in this directory with exactly 41
elements, one per target, each with keys:
`sku_id, product, retailer, url, name, price, availability, rating, status`.
`product` and `url` must come verbatim from `skus.json`.

## 3. Write new_listings.json

For each of the 10 products, run a web search (`mcp__brightdata__search_engine`
or `_batch`) for the product name plus "buy" and pick up to 5 result URLs
that sell the same product from a retailer domain that is **not** already
used anywhere in `skus.json` (exclude comparison/aggregator sites like
idealo, geizhals, pricerunner, camelcamelcamel; prefer real storefronts).

Write a JSON array to `new_listings.json` with one object per product:
`{"sku_id", "product", "new_retailer_urls": [...]}`.

## 4. Leave dashboard.html alone

`dashboard.html` already loads `results.json` at view-time — it does not
need to be regenerated. Just confirm it still exists.

## 5. Report

State how many of the 41 pages ended with `status == "ok"` (all four
fields collected).
