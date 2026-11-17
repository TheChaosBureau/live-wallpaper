# SPDX-License-Identifier: Apache-2.0
import fcntl
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fakes import JPEG, FakeDesktop, FakeFetcher
from live_wallpaper.app import KEEP_FRAMES, App, UserError
from live_wallpaper.cams import parse_cams
from live_wallpaper.desktop import DesktopError
from live_wallpaper.fetch import Fetched, FetchError
from live_wallpaper.state import Paths, State, load_state, save_state

UTC = timezone.utc
A_URL = "https://a.example/x.jpg"
ZUG = "https://www.foto-webcam.eu/webcam/zugspitze/"


def zug(key):
    return f"{ZUG}{key}_uh.jpg"


class Clock:
    def __init__(self):
        self.t = datetime(2026, 11, 17, 22, 3, tzinfo=UTC)

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += timedelta(**kw)


class Rig:
    def __init__(self, tmp_path):
        self.cams = {c.id: c for c in parse_cams([
            {"id": "a", "name": "A", "kind": "latest", "url": A_URL},
            {"id": "zug", "name": "Z", "kind": "foto-webcam", "url": "https://www.foto-webcam.eu",
             "cam": "zugspitze"},
            {"id": "earth", "name": "Earth", "kind": "latest", "url": "https://a.example/e.jpg",
             "fit": "scaled"},
        ])}
        self.paths = Paths(tmp_path / "state" / "state.json", tmp_path / "cache", tmp_path / "state" / "lock")
        self.fetcher = FakeFetcher({
            A_URL: Fetched("ok", JPEG, "V1"),
            "https://a.example/e.jpg": Fetched("ok", JPEG, None),
            zug("2026/11/17/2300"): Fetched("ok", JPEG, None),
            zug("2026/11/17/1400"): Fetched("ok", JPEG, None),
        })
        self.desktop = FakeDesktop({"picture-uri": "file:///photo.jpg",
                                    "picture-uri-dark": "file:///photo-dark.jpg",
                                    "picture-options": "zoom"})
        self.clock = Clock()
        self.app = App(self.cams, self.paths, self.fetcher, self.desktop, self.clock)

    @property
    def state(self):
        return load_state(self.paths.state_file)

    @property
    def uri(self):
        return self.desktop.values["picture-uri"]

    def frames(self):
        return sorted(p.name for p in self.paths.cache_dir.glob("*.jpg"))

    def urls(self):
        return [u for u, _ in self.fetcher.calls]


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_use_saves_original_and_sets_frame(rig):
    rig.app.use("a")
    assert rig.uri.startswith("file://" + str(rig.paths.cache_dir)) and rig.uri.endswith(".jpg")
    assert rig.desktop.values["picture-uri-dark"] == rig.uri
    assert Path(rig.uri.removeprefix("file://")).read_bytes() == JPEG
    assert rig.state.on and rig.state.cam == "a"
    assert rig.state.saved == {"picture-uri": "file:///photo.jpg",
                               "picture-uri-dark": "file:///photo-dark.jpg",
                               "picture-options": "zoom"}


def test_use_again_while_on_keeps_original_saved(rig):
    rig.app.use("a")
    rig.app.use("zug")
    rig.app.off()
    assert rig.uri == "file:///photo.jpg"
    assert rig.desktop.values["picture-uri-dark"] == "file:///photo-dark.jpg"
    assert rig.desktop.values["picture-options"] == "zoom"


def test_off_restores_and_stops_refreshing(rig):
    rig.app.use("a")
    rig.app.off()
    rig.fetcher.calls.clear()
    rig.clock.advance(hours=1)
    rig.app.refresh()
    assert rig.fetcher.calls == [] and rig.uri == "file:///photo.jpg"
    assert not rig.state.on and rig.state.saved is None


def test_off_when_already_off_changes_nothing(rig):
    rig.app.off()
    assert rig.uri == "file:///photo.jpg" and not rig.state.on


def test_off_then_on_again_saves_the_then_current_wallpaper(rig):
    rig.app.use("a")
    rig.app.off()
    rig.desktop.values["picture-uri"] = "file:///other.jpg"
    rig.app.use("a")
    rig.app.off()
    assert rig.uri == "file:///other.jpg"


def test_lost_state_does_not_save_a_cam_frame_as_the_original(rig):
    rig.app.use("a")
    rig.paths.state_file.write_text("")          # power loss
    rig.app.use("a")
    assert rig.state.saved is None
    with pytest.raises(UserError, match="no saved wallpaper"):
        rig.app.off()
    assert not rig.state.on


def test_unknown_cam_is_user_error_listing_ids(rig):
    with pytest.raises(UserError) as exc:
        rig.app.use("nope")
    assert "a" in str(exc.value) and "zug" in str(exc.value) and "nope" in str(exc.value)
    assert not rig.state.on


def test_use_fails_cleanly_without_a_desktop(rig):
    rig.desktop.fail = True
    with pytest.raises(UserError):
        rig.app.use("a")
    assert not rig.state.on


def test_offset_requires_cams_on(rig):
    with pytest.raises(UserError, match="off"):
        rig.app.set_offset(3)


def test_offset_on_latest_cam_refused(rig):
    rig.app.use("a")
    with pytest.raises(UserError, match="no archive"):
        rig.app.set_offset(3)


@pytest.mark.parametrize("hours", [24, -1])
def test_offset_range(rig, hours):
    rig.app.use("zug")
    with pytest.raises(UserError):
        rig.app.set_offset(hours)


def test_offset_shows_the_earlier_frame(rig):
    rig.app.use("zug")
    assert rig.state.shown_key == "2026/11/17/2300"
    rig.app.set_offset(9)
    assert rig.state.shown_key == "2026/11/17/1400"
    assert rig.state.frame_time == "2026-11-17T13:00:00+00:00"


def test_offset_remembered_per_cam(rig):
    rig.app.use("zug")
    rig.app.set_offset(9)
    rig.app.use("a")
    rig.fetcher.calls.clear()
    rig.app.use("zug")
    assert rig.urls()[0] == zug("2026/11/17/1400")


def test_steps_back_when_frame_missing(rig):
    save_state(rig.paths.state_file, State(offsets={"zug": 9}))
    del rig.fetcher.responses[zug("2026/11/17/1400")]
    rig.fetcher.responses[zug("2026/11/17/1340")] = Fetched("ok", JPEG, None)
    rig.app.use("zug")
    assert rig.urls() == [zug("2026/11/17/1400"), zug("2026/11/17/1350"), zug("2026/11/17/1340")]
    assert rig.state.shown_key == "2026/11/17/1340"


def test_steps_back_when_the_archive_answers_an_error_code(rig):
    # foto-webcam.eu answers 502, not 404, for a frame it does not have (seen live 2026-11-17)
    save_state(rig.paths.state_file, State(offsets={"zug": 9}))
    rig.fetcher.responses[zug("2026/11/17/1400")] = FetchError("www.foto-webcam.eu answered 502", status=502)
    rig.fetcher.responses[zug("2026/11/17/1350")] = Fetched("ok", JPEG, None)
    rig.app.use("zug")
    assert rig.state.shown_key == "2026/11/17/1350" and rig.state.last_error is None


def test_every_archive_frame_failing_reports_the_server_error(rig):
    for minute in ("1400", "1350", "1340", "1330", "1320", "1310", "1300"):
        rig.fetcher.responses[zug(f"2026/11/17/{minute}")] = FetchError("answered 502", status=502)
    save_state(rig.paths.state_file, State(offsets={"zug": 9}))
    rig.app.use("zug")
    assert len(rig.urls()) == 7
    assert "no frame" in rig.state.last_error and "502" in rig.state.last_error


def test_network_failure_stops_after_one_try(rig):
    save_state(rig.paths.state_file, State(offsets={"zug": 9}))
    rig.fetcher.responses[zug("2026/11/17/1400")] = FetchError("could not reach www.foto-webcam.eu")
    rig.app.use("zug")
    assert len(rig.urls()) == 1 and "could not reach" in rig.state.last_error


def test_identical_download_is_not_written_again(rig):
    # a server that ignores the validator and sends the same bytes again
    rig.app.use("a")
    shown = rig.uri
    rig.clock.advance(minutes=6)
    rig.app.refresh()
    assert rig.uri == shown and len(rig.frames()) == 1
    assert rig.state.fetched_at == rig.clock().isoformat()


def test_all_candidates_missing_keeps_frame_and_records_error(rig):
    rig.app.use("a")
    shown = rig.uri
    rig.fetcher.responses = {}
    rig.app.use("zug")
    assert rig.uri == shown
    assert "no frame" in rig.state.last_error
    assert len(rig.urls()) == 1 + 7


def test_same_frame_not_downloaded_twice(rig):
    rig.app.use("zug")
    rig.fetcher.calls.clear()
    rig.clock.advance(minutes=4)
    rig.app.refresh()
    assert rig.fetcher.calls == []


def test_next_slot_fetches_the_new_frame(rig):
    rig.app.use("zug")
    rig.fetcher.responses[zug("2026/11/17/2310")] = Fetched("ok", JPEG, None)
    rig.clock.advance(minutes=8)
    rig.app.refresh()
    assert rig.state.shown_key == "2026/11/17/2310"


def test_latest_cam_respects_interval_and_sends_validator(rig):
    rig.app.use("a")
    assert rig.fetcher.calls == [(A_URL, None)]
    rig.fetcher.calls.clear()
    rig.clock.advance(minutes=2)
    rig.app.refresh()
    assert rig.fetcher.calls == []
    rig.clock.advance(minutes=4)
    rig.app.refresh()
    assert rig.fetcher.calls == [(A_URL, "V1")]


def test_unchanged_keeps_file(rig):
    rig.app.use("a")
    shown = rig.uri
    rig.fetcher.responses[A_URL] = Fetched("unchanged", None, "V1")
    rig.clock.advance(minutes=6)
    rig.app.refresh()
    assert rig.uri == shown and rig.state.last_error is None
    assert rig.state.fetched_at == rig.clock().isoformat()


def test_fetch_error_keeps_frame_never_raises(rig):
    rig.app.use("a")
    shown = rig.uri
    rig.fetcher.responses[A_URL] = FetchError("could not reach a.example")
    rig.clock.advance(minutes=6)
    rig.app.refresh()
    assert rig.uri == shown and "could not reach" in rig.state.last_error


def test_error_clears_after_a_good_fetch(rig):
    rig.app.use("a")
    rig.fetcher.responses[A_URL] = FetchError("down")
    rig.clock.advance(minutes=6)
    rig.app.refresh()
    rig.fetcher.responses[A_URL] = Fetched("ok", JPEG + b"new", "V2")
    rig.clock.advance(minutes=5)
    rig.app.refresh()
    assert rig.state.last_error is None and rig.state.validator == "V2"


def test_desktop_error_in_refresh_never_raises(rig):
    rig.app.use("a")
    rig.desktop.fail = True
    rig.clock.advance(minutes=6)
    rig.app.refresh()
    assert "no session" in rig.state.last_error


def test_cam_removed_from_list(rig):
    rig.app.use("a")
    state = rig.state
    state.cam = "gone"
    save_state(rig.paths.state_file, state)
    rig.clock.advance(minutes=6)
    rig.app.refresh()
    assert "gone" in rig.state.last_error
    assert "Cam: gone (not in the cam list)" in rig.app.status()
    rig.app.off()
    assert rig.uri == "file:///photo.jpg"


def test_new_frame_gets_new_file_name_and_old_frames_pruned(rig):
    rig.app.use("a")
    seen = {rig.uri}
    for n in range(2):
        rig.fetcher.responses[A_URL] = Fetched("ok", JPEG + bytes([n]), "V1")
        rig.clock.advance(minutes=6)
        rig.app.refresh()
        seen.add(rig.uri)
    assert len(seen) == 3
    assert len(rig.frames()) == KEEP_FRAMES == 2
    assert Path(rig.uri.removeprefix("file://")).name in rig.frames()


def test_two_frames_in_the_same_second_get_different_names(rig):
    rig.app.use("a")
    first = rig.uri
    rig.app.use("earth")
    assert rig.uri != first


def test_fit_is_applied(rig):
    rig.app.use("earth")
    assert rig.desktop.values["picture-options"] == "scaled"
    rig.app.use("a")
    assert rig.desktop.values["picture-options"] == "zoom"


def test_refresh_returns_if_lock_held(rig):
    rig.app.use("a")
    rig.fetcher.calls.clear()
    rig.clock.advance(minutes=6)
    with open(rig.paths.lock_file, "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        rig.app.refresh()
    assert rig.fetcher.calls == []


def test_status_text(rig):
    assert rig.app.status() == "Cams: off"
    rig.app.use("a")
    assert rig.app.status() == "\n".join([
        "Cams: on", "Cam: A (a)", "Offset: live", "Updated: 2026-11-17 22:03"])
    rig.app.use("zug")
    rig.app.set_offset(9)
    assert rig.app.status() == "\n".join([
        "Cams: on", "Cam: Z (zug)", "Offset: 9 hours behind", "Frame: 2026-11-17 13:00",
        "Updated: 2026-11-17 22:03"])
    rig.app.set_offset(1)
    assert "Offset: 1 hour behind" in rig.app.status()
    assert "Last error: " in rig.app.status()       # no 22:00 CET frame in the fake


def test_list_cams_keeps_order(rig):
    assert [c.id for c in rig.app.list_cams()] == ["a", "zug", "earth"]
