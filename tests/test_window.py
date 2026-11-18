# SPDX-License-Identifier: Apache-2.0
"""The settings window, driven for real on a display (the package build gives it a virtual one)."""
import os
import time
from datetime import datetime, timezone

import pytest

if not os.environ.get("LIVE_WALLPAPER_WINDOW_TESTS"):  # the package build sets it, so it never skips these
    pytest.importorskip("gi")
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("no display", allow_module_level=True)

from gi.repository import GLib  # noqa: E402

from live_wallpaper import window as window_module  # noqa: E402
from live_wallpaper.app import UserError  # noqa: E402
from live_wallpaper.cams import parse_cams  # noqa: E402
from live_wallpaper.fetch import FetchError  # noqa: E402
from live_wallpaper.preview import Preview  # noqa: E402
from live_wallpaper.stamp import stamp  # noqa: E402

CAMS = parse_cams([
    {"id": "a", "name": "Cam A", "kind": "latest", "url": "https://a.example/x.jpg"},
    {"id": "zug", "name": "Zugspitze", "kind": "foto-webcam", "url": "https://www.foto-webcam.eu",
     "cam": "zugspitze"},
    {"id": "dead", "name": "Dead cam", "kind": "latest", "url": "https://a.example/dead.jpg"},
])


def jpeg() -> bytes:
    import io

    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (160, 90), "navy").save(out, "JPEG")
    return out.getvalue()


class FakeApp:
    def __init__(self):
        self.cam, self.hours, self.used, self.off_calls = None, 3, [], 0
        self.problem = None

    def list_cams(self):
        return list(CAMS)

    def current(self):
        return self.cam, 0

    def offset(self):
        return self.hours

    def local_time(self, when):
        return when.strftime("%Y-%m-%d %H:%M")

    def use(self, cam_id, hours=None):
        if cam_id == "dead":
            raise UserError("That cam is gone.")
        self.used.append((cam_id, hours))
        self.cam = next(c for c in CAMS if c.id == cam_id)
        return self.problem

    def off(self):
        self.off_calls += 1
        self.cam = None


class FakePreviewer:
    def __init__(self):
        self.calls = []

    def get(self, cam, hours=0):
        self.calls.append((cam.id, hours))
        if cam.id == "dead":
            raise FetchError("could not reach a.example")
        return Preview(jpeg(), datetime(2026, 11, 17, 13, 0, tzinfo=timezone.utc) if cam.supports_offset else None)


def pump(until, seconds=5.0):
    context, deadline = GLib.MainContext.default(), time.monotonic() + seconds
    while not until():
        assert time.monotonic() < deadline, "the window never got there"
        context.iteration(False)
        time.sleep(0.005)


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(window_module, "SLIDER_PAUSE_MS", 20)
    app, previewer = FakeApp(), FakePreviewer()
    win = window_module.Window(app, previewer)
    win.present()
    pump(lambda: not win.spinner.get_spinning())
    yield app, previewer, win
    win.destroy()


def select(win, cam_id):
    win.listbox.select_row(win._rows[cam_id])
    pump(lambda: not win.spinner.get_spinning())


def test_it_opens_on_the_first_cam_with_its_preview_and_changes_nothing(rig):
    app, previewer, win = rig
    assert win.title_label.get_label() == "Cam A"
    assert previewer.calls == [("a", 0)]
    assert win.picture.get_paintable() is not None
    assert win.frame_label.get_label() == "Live picture"
    assert not win.scale.get_sensitive() and win.set_button.get_sensitive()
    assert app.used == []


def test_clicking_a_cam_previews_it_at_the_offset(rig):
    app, previewer, win = rig
    select(win, "zug")
    assert previewer.calls[-1] == ("zug", 3)
    assert win.scale.get_sensitive() and win.hours == 3
    assert win.hours_label.get_label() == "3 hours behind live"
    assert win.frame_label.get_label() == "Picture taken 2026-11-17 13:00 (your time)"
    assert app.used == []


def test_dragging_the_slider_asks_for_one_preview_not_one_per_step(rig):
    app, previewer, win = rig
    select(win, "zug")
    before = len(previewer.calls)
    for hours in (4, 5, 6, 7):
        win.scale.set_value(hours)
    pump(lambda: len(previewer.calls) > before and not win.spinner.get_spinning())
    assert previewer.calls[before:] == [("zug", 7)]
    assert app.used == []


def test_set_as_wallpaper_applies_cam_and_offset_and_the_window_stays(rig):
    app, previewer, win = rig
    select(win, "zug")
    win.scale.set_value(9)
    win.set_button.emit("clicked")
    pump(lambda: app.used and win.set_button.get_sensitive())
    assert app.used == [("zug", 9)]
    assert win.status_label.get_label() == "Wallpaper set: Zugspitze, 9 hours behind live"
    assert win._marks["zug"].get_visible() and not win._marks["a"].get_visible()
    assert win.is_visible()
    select(win, "a")
    win.set_button.emit("clicked")
    pump(lambda: len(app.used) == 2 and win.set_button.get_sensitive())
    assert app.used[-1] == ("a", 9)
    assert win.status_label.get_label() == "Wallpaper set: Cam A"
    assert win._marks["a"].get_visible() and not win._marks["zug"].get_visible()


def test_a_cam_that_cannot_be_previewed_says_why_and_other_cams_still_work(rig):
    app, previewer, win = rig
    select(win, "dead")
    assert win.picture.get_paintable() is None
    assert win.frame_label.get_label() == "No preview: could not reach a.example"
    win.set_button.emit("clicked")
    pump(lambda: win.status_label.get_label() == "That cam is gone.")
    select(win, "a")
    assert win.picture.get_paintable() is not None


def test_a_wallpaper_whose_picture_could_not_be_fetched_is_reported(rig):
    app, previewer, win = rig
    app.problem = "could not reach a.example"
    win.set_button.emit("clicked")
    pump(lambda: app.used and win.set_button.get_sensitive())
    assert "could not be fetched yet: could not reach a.example" in win.status_label.get_label()


def test_search_narrows_the_list(rig):
    app, previewer, win = rig
    win.search.set_text("zug")
    shown = lambda: [cam_id for cam_id, row in win._rows.items() if row.get_child_visible()]  # noqa: E731
    pump(lambda: shown() == ["zug"])
    win.search.set_text("")
    pump(lambda: shown() == ["a", "zug", "dead"])


def test_back_to_photos_switches_cams_off(rig):
    app, previewer, win = rig
    win.set_button.emit("clicked")
    pump(lambda: app.used and win.off_button.get_sensitive())
    win.off_button.emit("clicked")
    pump(lambda: app.off_calls == 1 and win.off_button.get_sensitive())
    assert win.status_label.get_label() == "Cams are off. Your previous wallpaper is back."
    assert not any(mark.get_visible() for mark in win._marks.values())


def test_it_opens_on_the_cam_that_is_the_wallpaper(monkeypatch):
    app, previewer = FakeApp(), FakePreviewer()
    app.cam = CAMS[1]
    win = window_module.Window(app, previewer)
    pump(lambda: not win.spinner.get_spinning())
    assert win.title_label.get_label() == "Zugspitze" and win._marks["zug"].get_visible()
    win.destroy()


def test_the_offset_stays_where_the_user_put_it_when_the_cam_changes(rig):
    app, previewer, win = rig
    select(win, "zug")
    win.scale.set_value(7)
    pump(lambda: previewer.calls[-1] == ("zug", 7) and not win.spinner.get_spinning())
    select(win, "a")
    assert win.hours == 7 and not win.scale.get_sensitive()
    assert win.hours_label.get_label() == "Live only (no archive)"
    select(win, "zug")
    assert previewer.calls[-1] == ("zug", 7)
    assert win.hours == 7 and win.hours_label.get_label() == "7 hours behind live"
