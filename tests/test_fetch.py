# SPDX-License-Identifier: Apache-2.0
import io
import urllib.error
import urllib.request

import pytest

from fakes import JPEG
from live_wallpaper.fetch import MAX_BYTES, Fetched, FetchError, HttpFetcher, SameHostRedirect, check_jpeg

URL = "https://a.example/x.jpg"
HOSTS = frozenset({"a.example"})


class Response:
    def __init__(self, body=JPEG, headers=None, url=URL):
        self._body = io.BytesIO(body)
        self.headers = headers or {}
        self._url = url
        self.status = 200

    def read(self, n=-1):
        return self._body.read(n)

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Opener:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def fetcher(result):
    opener = Opener(result)
    return HttpFetcher(HOSTS, "live-wallpaper/0.1.0", opener=opener), opener


def http_error(code):
    return urllib.error.HTTPError(URL, code, "x", {}, None)


def test_ok_returns_data_and_validator():
    f, _ = fetcher(Response(headers={"Last-Modified": "Tue, 17 Nov 2026 22:02:20 GMT"}))
    assert f.get(URL) == Fetched("ok", JPEG, "Tue, 17 Nov 2026 22:02:20 GMT")


def test_etag_preferred_as_validator():
    f, _ = fetcher(Response(headers={"ETag": '"abc"', "Last-Modified": "Tue, 17 Nov 2026 22:02:20 GMT"}))
    assert f.get(URL).validator == '"abc"'


def test_sends_user_agent_and_date_validator():
    f, opener = fetcher(Response())
    f.get(URL, "Tue, 17 Nov 2026 22:02:20 GMT")
    (req,) = opener.requests
    assert req.get_header("User-agent") == "live-wallpaper/0.1.0"
    assert req.get_header("If-modified-since") == "Tue, 17 Nov 2026 22:02:20 GMT"
    assert req.get_header("If-none-match") is None


def test_sends_etag_validator_as_if_none_match():
    f, opener = fetcher(Response())
    f.get(URL, '"abc"')
    assert opener.requests[0].get_header("If-none-match") == '"abc"'


def test_304_is_unchanged():
    f, _ = fetcher(http_error(304))
    assert f.get(URL, "v") == Fetched("unchanged", None, "v")


def test_404_is_missing():
    f, _ = fetcher(http_error(404))
    assert f.get(URL).status == "missing"


def test_500_raises_fetch_error():
    f, _ = fetcher(http_error(500))
    with pytest.raises(FetchError):
        f.get(URL)


def test_http_scheme_refused_before_any_request():
    f, opener = fetcher(Response())
    with pytest.raises(FetchError):
        f.get("http://a.example/x.jpg")
    assert opener.requests == []


def test_host_not_in_allowlist_refused_before_any_request():
    f, opener = fetcher(Response())
    with pytest.raises(FetchError):
        f.get("https://evil.example/x.jpg")
    assert opener.requests == []


def test_final_url_on_other_host_refused():
    f, _ = fetcher(Response(url="https://evil.example/x.jpg"))
    with pytest.raises(FetchError):
        f.get(URL)


@pytest.mark.parametrize("target", ["https://evil.example/x.jpg", "http://a.example/x.jpg"])
def test_redirect_handler_refuses_other_host_or_scheme(target):
    req = urllib.request.Request(URL)
    with pytest.raises(FetchError):
        SameHostRedirect().redirect_request(req, None, 302, "Found", {}, target)


def test_redirect_handler_allows_same_host():
    req = urllib.request.Request(URL)
    new = SameHostRedirect().redirect_request(req, None, 302, "Found", {}, "https://a.example/y.jpg")
    assert new.full_url == "https://a.example/y.jpg"


def test_html_body_with_200_rejected():
    f, _ = fetcher(Response(body=b"<html>not found</html>"))
    with pytest.raises(FetchError, match="not a JPEG"):
        f.get(URL)


def test_empty_body_rejected():
    with pytest.raises(FetchError):
        check_jpeg(b"")


def test_body_over_limit_rejected_without_reading_it_all():
    class Endless:
        def __init__(self):
            self.asked = 0

        def read(self, n=-1):
            assert n > 0, "must read with a bound"
            self.asked += n
            return b"\xff\xd8\xff" + b"0" * (n - 3)

    r = Response()
    r._body = Endless()
    f, _ = fetcher(r)
    with pytest.raises(FetchError, match="too large"):
        f.get(URL)
    assert r._body.asked <= MAX_BYTES + 1


def test_network_error_becomes_fetch_error():
    f, _ = fetcher(urllib.error.URLError("no route"))
    with pytest.raises(FetchError):
        f.get(URL)


def test_timeout_becomes_fetch_error():
    f, _ = fetcher(TimeoutError("slow"))
    with pytest.raises(FetchError):
        f.get(URL)
