# SPDX-License-Identifier: Apache-2.0
import dataclasses
from datetime import datetime, timezone

import pytest

from live_wallpaper.cams import Cam
from live_wallpaper.frames import STEP_BACK_LIMIT, Candidate, candidates

UTC = timezone.utc
ZUG = Cam(id="zug", name="Z", kind="foto-webcam", url="https://www.foto-webcam.eu", cam="zugspitze")
LATEST = Cam(id="a", name="A", kind="latest", url="https://a.example/x.jpg")


def test_latest_cam_single_candidate():
    assert candidates(LATEST, 0, datetime(2026, 11, 17, 22, 3, tzinfo=UTC)) == [
        Candidate("https://a.example/x.jpg", None, None)]


def test_latest_cam_rejects_offset():
    with pytest.raises(ValueError):
        candidates(LATEST, 3, datetime(2026, 11, 17, tzinfo=UTC))


def test_naive_now_rejected():
    with pytest.raises(ValueError):
        candidates(ZUG, 0, datetime(2026, 11, 17, 22, 3))


def test_foto_webcam_offset_rounds_down_in_cam_zone():
    got = candidates(ZUG, 9, datetime(2026, 11, 17, 22, 3, tzinfo=UTC))
    assert got[0].url == "https://www.foto-webcam.eu/webcam/zugspitze/2026/11/17/1400_uh.jpg"
    assert got[0].key == "2026/11/17/1400"
    assert got[0].frame_time == datetime(2026, 11, 17, 13, 0, tzinfo=UTC)


def test_foto_webcam_steps_back_by_interval():
    got = candidates(ZUG, 9, datetime(2026, 11, 17, 22, 3, tzinfo=UTC))
    assert len(got) == STEP_BACK_LIMIT + 1
    assert [c.key for c in got] == ["2026/11/17/1400", "2026/11/17/1350", "2026/11/17/1340",
                                    "2026/11/17/1330", "2026/11/17/1320", "2026/11/17/1310",
                                    "2026/11/17/1300"]


def test_offset_crosses_midnight():
    got = candidates(ZUG, 9, datetime(2026, 11, 17, 5, 0, tzinfo=UTC))
    assert got[0].key == "2026/11/16/2100"


def test_offset_is_real_hours_across_dst_change():
    got = candidates(ZUG, 9, datetime(2026, 10, 25, 5, 0, tzinfo=UTC))
    assert got[0].key == "2026/10/24/2200"


def test_now_in_another_zone_gives_the_same_frame():
    pst = timezone(datetime(2026, 1, 1, 8, tzinfo=UTC) - datetime(2026, 1, 1, 16, tzinfo=UTC))
    got = candidates(ZUG, 9, datetime(2026, 11, 17, 14, 3, tzinfo=pst))
    assert got[0].key == "2026/11/17/1400"


def test_interval_and_size_come_from_the_cam():
    c = dataclasses.replace(ZUG, interval_minutes=30, size="hu")
    got = candidates(c, 0, datetime(2026, 11, 17, 11, 44, tzinfo=UTC))
    assert got[0].url.endswith("/2026/11/17/1230_hu.jpg") and got[1].key == "2026/11/17/1200"
