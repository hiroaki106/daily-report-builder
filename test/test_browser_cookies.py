import unittest
from http.cookiejar import Cookie, CookieJar
from unittest.mock import patch

from app.browser_cookies import BrowserCookieError, load_chrome_cookies


def _cookie_jar() -> CookieJar:
    jar = CookieJar()
    jar.set_cookie(
        Cookie(
            version=0,
            name="session",
            value="cookie-value",
            port=None,
            port_specified=False,
            domain="example.atlassian.net",
            domain_specified=True,
            domain_initial_dot=False,
            path="/",
            path_specified=True,
            secure=True,
            expires=None,
            discard=True,
            comment=None,
            comment_url=None,
            rest={},
            rfc2109=False,
        )
    )
    return jar


class LoadChromeCookiesTest(unittest.TestCase):
    @patch("app.browser_cookies.browser_cookie3.chrome")
    def test_loads_only_base_url_domain(self, chrome: object) -> None:
        chrome.return_value = _cookie_jar()  # type: ignore[attr-defined]

        cookies = load_chrome_cookies("https://example.atlassian.net/wiki")

        self.assertEqual(len(cookies), 1)
        chrome.assert_called_once_with(  # type: ignore[attr-defined]
            domain_name="example.atlassian.net"
        )

    @patch("app.browser_cookies.browser_cookie3.chrome")
    def test_raises_when_no_cookie_is_found(self, chrome: object) -> None:
        chrome.return_value = CookieJar()  # type: ignore[attr-defined]

        with self.assertRaisesRegex(BrowserCookieError, "No Chrome cookies found"):
            load_chrome_cookies("https://example.atlassian.net")


if __name__ == "__main__":
    unittest.main()
