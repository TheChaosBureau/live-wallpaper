# SPDX-License-Identifier: Apache-2.0
"""Fetching a frame: HTTPS only, listed hosts only, real JPEGs only."""

from __future__ import annotations

import http.client
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

MAX_BYTES = 25 * 1024 * 1024
TIMEOUT_S = 30
_JPEG_MAGIC = b"\xff\xd8\xff"


class FetchError(Exception):
    """A frame could not be fetched, or what came back is not usable.

    ``status`` is the HTTP status when the server answered with an error code,
    and None for everything else (network failure, refused URL, bad content).
    """

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class Fetched:
    status: str  # "ok", "unchanged" or "missing"
    data: bytes | None
    validator: str | None


class Fetcher(Protocol):
    def get(self, url: str, validator: str | None = None) -> Fetched: ...


def check_jpeg(data: bytes) -> None:
    if not data.startswith(_JPEG_MAGIC):
        raise FetchError("the server did not send an image (not a JPEG)")


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only if it stays on the same host and on HTTPS."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        try:
            same_port = (new.port or 443) == (old.port or 443)
        except ValueError:
            same_port = False
        if new.scheme != "https" or new.hostname != old.hostname or not same_port:
            raise FetchError(f"refused a redirect from {old.hostname} to {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HttpFetcher:
    def __init__(self, allowed_hosts: frozenset[str], user_agent: str, opener=None):
        self._hosts = allowed_hosts
        self._user_agent = user_agent
        # No proxies, whatever the environment says: requests go to the listed hosts only.
        self._opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}), SameHostRedirect())

    def _check_url(self, url: str) -> str:
        parts = urlsplit(url)
        if parts.scheme != "https":
            raise FetchError(f"refused {url}: only https is allowed")
        if parts.hostname not in self._hosts:
            raise FetchError(f"refused {url}: {parts.hostname} is not in the cam list")
        return parts.hostname

    def get(self, url: str, validator: str | None = None) -> Fetched:
        host = self._check_url(url)
        headers = {"User-Agent": self._user_agent, "Accept": "image/jpeg"}
        if validator:
            is_etag = validator.startswith(('"', "W/"))
            headers["If-None-Match" if is_etag else "If-Modified-Since"] = validator
        request = urllib.request.Request(url, headers=headers)
        try:
            with self._opener.open(request, timeout=TIMEOUT_S) as response:
                if urlsplit(response.geturl()).hostname != host:
                    raise FetchError(f"refused {url}: answered from another host")
                data = response.read(MAX_BYTES + 1)
                new_validator = response.headers.get("ETag") or response.headers.get("Last-Modified")
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return Fetched("unchanged", None, validator)
            if exc.code == 404:
                return Fetched("missing", None, None)
            raise FetchError(f"{host} answered {exc.code}", status=exc.code) from exc
        except FetchError:
            raise
        except (urllib.error.URLError, OSError, http.client.HTTPException, UnicodeError) as exc:
            reason = getattr(exc, "reason", exc)
            raise FetchError(f"could not reach {host}: {reason}") from exc
        if len(data) > MAX_BYTES:
            raise FetchError(f"{host} sent a file that is too large")
        check_jpeg(data)
        return Fetched("ok", data, new_validator)
