import sys; sys.path.insert(0, "scripts")
from mcp_client import call
call("scrape_as_markdown", {"url": "https://www.bestbuy.com/product/sony-wh-1000xm6-best-wireless-noise-cancelling-headphones-black/J7XSRH5RCF/sku/6620467"})
call("search_engine", {"query": "sony wh-1000xm6 price best buy"})
