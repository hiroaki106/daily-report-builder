"""Browser cookie loading helpers."""

from __future__ import annotations

from http.cookiejar import CookieJar
from urllib.parse import urlparse

import browser_cookie3


class BrowserCookieError(RuntimeError):
    """Raised when browser cookies cannot be loaded."""


def load_chrome_cookies(base_url: str) -> CookieJar:
    """Load Chrome cookies restricted to the hostname in ``base_url``."""
    hostname = urlparse(base_url).hostname
    if hostname is None:
        raise BrowserCookieError(f"Invalid base URL: {base_url!r}")

    try:
        cookies = browser_cookie3.chrome(domain_name=hostname)
    except Exception as exc:
        raise BrowserCookieError(
            f"Could not load Chrome cookies for {hostname}: {exc}"
        ) from exc

    if not any(True for _ in cookies):
        raise BrowserCookieError(f"No Chrome cookies found for {hostname}")

    return cookies
