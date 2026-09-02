"""HTTP + browser fetch helpers for the competitor price tracker.

Two fetch strategies are used:
  1. `fetch_static` - a fast plain HTTP GET using curl_cffi with a Chrome TLS
     fingerprint. Works for most retailers (Best Buy, Walmart, and Amazon
     once a US delivery-locale cookie pair is set).
  2. `fetch_rendered` - a headless-Chrome fetch via patchright (a
     detection-hardened Playwright fork). Needed for retailers whose price
     is injected client-side after page load (Target), and used as a
     fallback for any retailer whose static fetch came back incomplete.

No login/credentials are ever used. The only cookies set are public,
unauthenticated locale/delivery preferences (equivalent to a visitor
manually picking "Ship to: United States, USD" in a site's UI).
"""
import time

from curl_cffi import requests as cffi_requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Public, unauthenticated locale-preference cookies (no login/credentials).
# These simply tell each site "show me the US-dollar storefront", the same
# choice a human visitor can make from the site's own country/currency menu.
LOCALE_COOKIES = {
    "amazon": {"i18n-prefs": "USD", "lc-main": "en_US"},
}


def fetch_static(url, retailer, timeout=20):
    cookies = LOCALE_COOKIES.get(retailer, {})
    try:
        resp = cffi_requests.get(
            url,
            impersonate="chrome",
            timeout=timeout,
            cookies=cookies,
            headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        return resp.text, resp.status_code, None
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"


class BrowserFetcher:
    """Wraps a single reusable patchright (undetected Playwright) browser."""

    def __init__(self):
        self._pw = None
        self._browser = None

    def start(self):
        from patchright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(headless=True, channel="chrome")
        except Exception:
            self._browser = self._pw.chromium.launch(headless=True)

    def stop(self):
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()

    def fetch(self, url, retailer, timeout_ms=30000, settle_ms=3500, wait_selector=None):
        if self._browser is None:
            self.start()
        cookies = LOCALE_COOKIES.get(retailer, {})
        ctx = self._browser.new_context(user_agent=USER_AGENT, locale="en-US")
        if cookies:
            try:
                domain = {
                    "amazon": ".amazon.com",
                }.get(retailer)
                ctx.add_cookies(
                    [
                        {"name": k, "value": v, "domain": domain, "path": "/"}
                        for k, v in cookies.items()
                    ]
                )
            except Exception:
                pass
        page = ctx.new_page()
        html, err = None, None
        try:
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            page.wait_for_timeout(settle_ms)
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=8000)
                except Exception:
                    pass
            for attempt in range(3):
                try:
                    html = page.content()
                    break
                except Exception:
                    time.sleep(1)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
        finally:
            try:
                page.close()
            except Exception:
                pass
            try:
                ctx.close()
            except Exception:
                pass
        return html, err


WAIT_SELECTORS = {
    "target": '[data-test="product-price"]',
}
