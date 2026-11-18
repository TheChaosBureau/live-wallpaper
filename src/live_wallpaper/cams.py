# SPDX-License-Identifier: Apache-2.0
"""The cam list: what a cam is, and loading it from JSON files."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

KINDS = ("latest", "foto-webcam")
FITS = ("zoom", "scaled")
_ID = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
_SIZE = re.compile(r"[a-z0-9]+\Z")
_FIELDS = {"id", "name", "kind", "url", "cam", "interval_minutes", "timezone", "size", "fit", "credit"}
_DEFAULT_INTERVAL = {"latest": 5, "foto-webcam": 10}


class CamError(ValueError):
    """A cam list is malformed."""


@dataclass(frozen=True)
class Cam:
    id: str
    name: str
    kind: str
    url: str
    cam: str | None = None
    interval_minutes: int | None = None
    timezone: str = "Europe/Berlin"
    size: str = "uh"
    fit: str = "zoom"
    credit: str | None = None

    def __post_init__(self) -> None:
        if self.interval_minutes is None:
            object.__setattr__(self, "interval_minutes", _DEFAULT_INTERVAL.get(self.kind, 5))

    @property
    def supports_offset(self) -> bool:
        return self.kind == "foto-webcam"

    @property
    def host(self) -> str:
        return urlsplit(self.url).hostname or ""


def _parse_one(raw: object, where: str) -> Cam:
    if not isinstance(raw, dict):
        raise CamError(f"{where}: a cam must be an object")
    cam_id = raw.get("id")
    if not isinstance(cam_id, str) or not _ID.match(cam_id):
        raise CamError(f"{where}: id must be lower-case letters, digits and dashes")
    where = f"cam {cam_id!r}"
    unknown = set(raw) - _FIELDS
    if unknown:
        raise CamError(f"{where}: unknown field {sorted(unknown)[0]!r}")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise CamError(f"{where}: name is required")
    kind = raw.get("kind")
    if kind not in KINDS:
        raise CamError(f"{where}: kind must be one of {', '.join(KINDS)}")
    url = raw.get("url")
    parts = urlsplit(url) if isinstance(url, str) else None
    if parts is None or parts.scheme != "https" or not parts.hostname:
        raise CamError(f"{where}: url must be an https:// address")
    if parts.username or parts.password:
        raise CamError(f"{where}: url must not contain a user name or password")
    site_cam = raw.get("cam")
    if kind == "foto-webcam":
        if not isinstance(site_cam, str) or not _ID.match(site_cam):
            raise CamError(f"{where}: cam (the site's cam id) is required for foto-webcam")
        url = url.rstrip("/")
    interval = raw.get("interval_minutes", _DEFAULT_INTERVAL[kind])
    if isinstance(interval, bool) or not isinstance(interval, int) or not 1 <= interval <= 1440:
        raise CamError(f"{where}: interval_minutes must be a whole number from 1 to 1440")
    tz = raw.get("timezone", "Europe/Berlin")
    try:
        if not isinstance(tz, str):
            raise ValueError
        ZoneInfo(tz)
    except Exception as exc:
        raise CamError(f"{where}: timezone {tz!r} is not a known time zone") from exc
    size = raw.get("size", "uh")
    if not isinstance(size, str) or not _SIZE.match(size):
        raise CamError(f"{where}: size must be letters and digits")
    fit = raw.get("fit", "zoom")
    if fit not in FITS:
        raise CamError(f"{where}: fit must be one of {', '.join(FITS)}")
    credit = raw.get("credit")
    if credit is not None and (not isinstance(credit, str) or not credit.strip()
                               or len(credit) > 80 or not credit.isprintable()):
        raise CamError(f"{where}: credit must be one short line of text (at most 80 characters)")
    return Cam(id=cam_id, name=name, kind=kind, url=url, cam=site_cam,
               interval_minutes=interval, timezone=tz, size=size, fit=fit, credit=credit)


def parse_cams(raw: object) -> list[Cam]:
    if not isinstance(raw, list):
        raise CamError("a cam list must be a JSON list")
    return [_parse_one(item, f"entry {i + 1}") for i, item in enumerate(raw)]


def load_cams(paths: list[Path]) -> dict[str, Cam]:
    cams: dict[str, Cam] = {}
    for path in paths:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise CamError(f"{path}: {exc}") from exc
        try:
            raw = json.loads(text)
        except ValueError as exc:
            raise CamError(f"{path}: not valid JSON ({exc})") from exc
        try:
            parsed = parse_cams(raw)
        except CamError as exc:
            raise CamError(f"{path}: {exc}") from exc
        for cam in parsed:
            cams[cam.id] = cam
    return cams


BUILTIN_FILES = 2


def default_cam_paths(env: dict[str, str] | None = None) -> list[Path]:
    env = os.environ if env is None else env
    config = env.get("XDG_CONFIG_HOME") or os.path.join(env.get("HOME", "/"), ".config")
    return [
        Path(__file__).parent / "data" / "cams.json",
        Path(__file__).parent / "data" / "foto-webcam.json",
        Path("/etc/live-wallpaper/cams.json"),
        Path(config) / "live-wallpaper" / "cams.json",
    ]


def allowed_hosts(cams: dict[str, Cam]) -> frozenset[str]:
    return frozenset(cam.host for cam in cams.values())
