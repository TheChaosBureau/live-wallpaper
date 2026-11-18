# SPDX-License-Identifier: Apache-2.0
"""Which frame of a cam to show for a given time offset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .cams import Cam

STEP_BACK_LIMIT = 6


@dataclass(frozen=True)
class Candidate:
    url: str
    key: str | None
    frame_time: datetime | None


def candidates(cam: Cam, offset_hours: int, now: datetime, size: str | None = None) -> list[Candidate]:
    """Frame URLs to try, newest first. `size` asks an archive for another image size."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if cam.kind == "latest":
        if offset_hours != 0:
            raise ValueError(f"{cam.id} has no archive, so it has no time offset")
        return [Candidate(cam.url, None, None)]

    zone = ZoneInfo(cam.timezone)
    interval = cam.interval_minutes
    local = (now - timedelta(hours=offset_hours)).astimezone(zone)
    minute_of_day = local.hour * 60 + local.minute
    floored = minute_of_day - minute_of_day % interval
    first = local.replace(hour=floored // 60, minute=floored % 60, second=0, microsecond=0)
    first_utc = first.astimezone(timezone.utc)

    out = []
    for step in range(STEP_BACK_LIMIT + 1):
        frame_utc = first_utc - timedelta(minutes=interval * step)
        key = frame_utc.astimezone(zone).strftime("%Y/%m/%d/%H%M")
        out.append(Candidate(f"{cam.url}/webcam/{cam.cam}/{key}_{size or cam.size}.jpg", key, frame_utc))
    return out
