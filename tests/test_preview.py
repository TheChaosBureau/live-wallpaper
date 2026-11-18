# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta, timezone

import pytest

from fakes import JPEG, FakeFetcher
from live_wallpaper.cams import parse_cams
from live_wallpaper.fetch import Fetched, FetchError
from live_wallpaper.preview import KEEP_PREVIEWS, Previewer

A_URL = "https://a.example/x.jpg"
A, ZUG, PLAIN = parse_cams([
    {"id": "a", "name": "A", "kind": "latest", "url": A_URL},
    {"id": "zug", "name": "Z", "kind": "foto-webcam", "url": "https://www.foto-webcam.eu",
     "cam": "zugspitze", "credit": "www.foto-webcam.eu"},
    {"id": "plain", "name": "P", "kind": "foto-webcam", "url": "https://www.foto-webcam.eu", "cam": "plain"},
])


def zug(key):
    return f"https://www.foto-webcam.eu/webcam/zugspitze/{key}_la.jpg"


class Rig:
    def __init__(self, responses):
        self.t = datetime(2026, 11, 17, 22, 3, tzinfo=timezone.utc)  # 23:03 in Berlin
        self.fetcher = FakeFetcher(responses)
        self.previewer = Previewer(self.fetcher, lambda: self.t, stamp=lambda data, text: data + text.encode())


def test_a_live_cam_is_fetched_whole_and_has_no_frame_time():
    rig = Rig({A_URL: Fetched("ok", JPEG, "V1")})
    preview = rig.previewer.get(A)
    assert preview.data == JPEG and preview.frame_time is None
    assert rig.fetcher.calls == [(A_URL, None)]


def test_an_archive_cam_is_fetched_small_at_the_offset_and_credited():
    rig = Rig({zug("2026/11/17/1400"): Fetched("ok", JPEG, None)})
    preview = rig.previewer.get(ZUG, 9)
    assert preview.data == JPEG + b"www.foto-webcam.eu"
    assert preview.frame_time == datetime(2026, 11, 17, 13, 0, tzinfo=timezone.utc)
    assert rig.fetcher.calls == [(zug("2026/11/17/1400"), None)]


def test_a_frame_the_archive_does_not_have_falls_back_to_the_one_before():
    rig = Rig({zug("2026/11/17/2300"): FetchError("502", status=502),
               zug("2026/11/17/2240"): Fetched("ok", JPEG, None)})
    assert rig.previewer.get(ZUG).frame_time == datetime(2026, 11, 17, 21, 40, tzinfo=timezone.utc)


def test_no_frame_at_all_is_an_error():
    with pytest.raises(FetchError, match="no picture available for Z"):
        Rig({}).previewer.get(ZUG)


def test_a_network_failure_is_not_retried_on_older_frames():
    rig = Rig({zug("2026/11/17/2300"): FetchError("could not reach")})
    with pytest.raises(FetchError, match="could not reach"):
        rig.previewer.get(ZUG)
    assert len(rig.fetcher.calls) == 1


def test_a_preview_is_kept_for_five_minutes():
    rig = Rig({A_URL: Fetched("ok", JPEG, None)})
    rig.previewer.get(A)
    rig.t += timedelta(minutes=4)
    rig.previewer.get(A)
    assert len(rig.fetcher.calls) == 1
    rig.t += timedelta(minutes=2)
    rig.previewer.get(A)
    assert len(rig.fetcher.calls) == 2


def test_each_offset_is_its_own_preview_but_a_live_cam_ignores_the_offset():
    rig = Rig({A_URL: Fetched("ok", JPEG, None),
               zug("2026/11/17/2300"): Fetched("ok", JPEG, None),
               zug("2026/11/17/2200"): Fetched("ok", JPEG, None)})
    rig.previewer.get(ZUG, 0), rig.previewer.get(ZUG, 1), rig.previewer.get(ZUG, 0)
    assert len(rig.fetcher.calls) == 2
    rig.previewer.get(A, 5), rig.previewer.get(A, 0)
    assert len(rig.fetcher.calls) == 3


def test_a_failure_is_not_kept():
    rig = Rig({A_URL: FetchError("could not reach")})
    with pytest.raises(FetchError):
        rig.previewer.get(A)
    rig.fetcher.responses[A_URL] = Fetched("ok", JPEG, None)
    assert rig.previewer.get(A).data == JPEG


def test_only_so_many_previews_are_kept():
    rig = Rig({zug("2026/11/17/2300"): Fetched("ok", JPEG, None)})
    rig.fetcher.get = lambda url, validator=None: Fetched("ok", JPEG, None)
    for hours in range(24):
        rig.previewer.get(ZUG, hours)
    rig.previewer.get(PLAIN)
    assert len(rig.previewer._kept) == KEEP_PREVIEWS
    assert ("zug", 0) not in rig.previewer._kept and ("plain", 0) in rig.previewer._kept
