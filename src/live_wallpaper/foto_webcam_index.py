# SPDX-License-Identifier: Apache-2.0
"""Turning the foto-webcam.eu camera index into cam entries.

Used by tools/update_foto_webcam.py to regenerate data/foto-webcam.json; the
app itself never fetches the index.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

SITE = "https://www.foto-webcam.eu"
HOST = "www.foto-webcam.eu"
CREDIT = "www.foto-webcam.eu"
_ID = re.compile(r"[a-z0-9][a-z0-9-]*\Z")


def _interval_minutes(raw: object) -> int | None:
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        return None
    if seconds in (600, 1800):
        return 10   # these cameras archive a frame every 10 minutes
    if seconds == 3600:
        return 60
    return None     # stopped, yearly or otherwise unusual cameras


def cams_from_index(index: dict) -> list[dict]:
    """Cam entries for the site's own running cameras, sorted by name."""
    cams = []
    for entry in index.get("cams", []):
        site_id = entry.get("id")
        name = " ".join(str(entry.get("title") or "").split())
        interval = _interval_minutes(entry.get("captureInterval"))
        if (not isinstance(site_id, str) or not _ID.match(site_id) or not name or interval is None
                or entry.get("offline") or entry.get("hidden") or entry.get("partner")
                or urlsplit(str(entry.get("imgurl") or "")).hostname != HOST):
            continue
        cams.append({"id": f"alps-{site_id}", "name": name, "kind": "foto-webcam", "url": SITE,
                     "cam": site_id, "interval_minutes": interval, "fit": "scaled", "credit": CREDIT})
    return sorted(cams, key=lambda cam: (cam["name"].casefold(), cam["id"]))
