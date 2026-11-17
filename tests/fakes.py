# SPDX-License-Identifier: Apache-2.0
"""Test doubles for the two outside-world seams."""

from live_wallpaper.fetch import Fetched

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100


class FakeFetcher:
    def __init__(self, responses=None):
        self.responses = dict(responses or {})
        self.calls = []

    def get(self, url, validator=None):
        self.calls.append((url, validator))
        response = self.responses.get(url, Fetched("missing", None, None))
        if isinstance(response, Exception):
            raise response
        return response


class FakeDesktop:
    def __init__(self, values):
        self.values = values
        self.fail = False

    def get(self, key):
        from live_wallpaper.desktop import DesktopError
        if self.fail:
            raise DesktopError("no session")
        return self.values[key]

    def set(self, key, value):
        from live_wallpaper.desktop import DesktopError
        if self.fail:
            raise DesktopError("no session")
        self.values[key] = value
