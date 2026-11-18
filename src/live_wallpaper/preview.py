# SPDX-License-Identifier: Apache-2.0
"""A small picture of a cam, for the settings window. Changes nothing on disk."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from .cams import Cam
from .fetch import Fetcher, FetchError
from .frames import candidates
from .stamp import stamp as draw_credit

# The archive's "large" size: about 80 kB, against about 800 kB for the wallpaper size.
PREVIEW_SIZE = "la"
KEEP_FOR = timedelta(minutes=5)
KEEP_PREVIEWS = 24


@dataclass(frozen=True)
class Preview:
    data: bytes
    frame_time: datetime | None  # None for a cam that only has a live picture


class Previewer:
    """Fetches previews, and keeps each for five minutes so a cam looked at
    twice costs its site one request."""

    def __init__(self, fetcher: Fetcher, now: Callable[[], datetime],
                 stamp: Callable[[bytes, str], bytes] = draw_credit):
        self._fetcher = fetcher
        self._now = now
        self._stamp = stamp
        self._kept: dict[tuple[str, int], tuple[datetime, Preview]] = {}
        self._guard = threading.Lock()

    def get(self, cam: Cam, hours: int = 0) -> Preview:
        """The cam's picture `hours` behind live. Raises FetchError."""
        hours = hours if cam.supports_offset else 0
        now = self._now()
        key = (cam.id, hours)
        with self._guard:
            kept = self._kept.get(key)
            if kept and timedelta(0) <= now - kept[0] < KEEP_FOR:
                return kept[1]
        preview = self._fetch(cam, hours, now)
        with self._guard:
            self._kept.pop(key, None)
            self._kept[key] = (now, preview)
            while len(self._kept) > KEEP_PREVIEWS:
                del self._kept[next(iter(self._kept))]
        return preview

    def _fetch(self, cam: Cam, hours: int, now: datetime) -> Preview:
        server_error = None
        for candidate in candidates(cam, hours, now, size=PREVIEW_SIZE):
            try:
                fetched = self._fetcher.get(candidate.url)
            except FetchError as exc:
                # an archive answers an error code for a frame it does not have
                if candidate.key is None or exc.status is None:
                    raise
                server_error = exc
                continue
            if fetched.status != "ok" or not fetched.data:
                continue
            data = self._stamp(fetched.data, cam.credit) if cam.credit else fetched.data
            return Preview(data, candidate.frame_time)
        detail = f" ({server_error})" if server_error else ""
        raise FetchError(f"no picture available for {cam.name} at that time{detail}")
