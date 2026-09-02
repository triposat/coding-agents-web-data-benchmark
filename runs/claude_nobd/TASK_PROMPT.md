Build a competitor price tracker.

`skus.json` in this directory lists 10 products. Each product has a `retailers`
object mapping a retailer name to a product page `url`. There are 41 product
pages in total.

Requirements:

1. For every one of the 41 product pages, collect four fields:
   - product name
   - current price
   - availability
   - customer rating
2. Write the results to `results.json` in this directory, as a JSON array. Each
   element must have the keys: `sku_id`, `product`, `retailer`, `url`, `name`,
   `price`, `availability`, `rating`, `status`. Use `null` for any field you
   could not collect. Set `status` to "ok" if you got the data and to a short
   reason string if you did not.
3. Also produce a `new_listings.json`: for each of the 10 products, run a web
   search and record up to 5 additional retailer URLs selling the same product
   that are not already in `skus.json`.
4. Build a single self-contained `dashboard.html` that loads `results.json` and
   shows a table of every product with its price at each retailer, so the
   cheapest retailer per product is visible.

Constraints:

- Public pages only. Do not attempt to log in, and do not use any credentials.
- Do not modify `skus.json`. Every run must chase the same targets.
- The tracker must be runnable again later by executing a single command. Put
  that command in `README.md`.

Report at the end how many of the 41 pages you successfully collected all four
fields for.
