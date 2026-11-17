# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import pytest

from live_wallpaper.state import Paths, State, load_state, save_state


def test_missing_file_is_default(tmp_path):
    assert load_state(tmp_path / "nope.json") == State()


@pytest.mark.parametrize("content", [
    "", "{", "[]", '{"on": "yes", "offsets": 3}', '{"offsets": {"zug": "nine"}}',
    '{"saved": {"picture-uri": 3}}', '{"cam": 7}', "\x00\x00\x00",
])
def test_bad_file_is_default(tmp_path, content):
    p = tmp_path / "state.json"
    p.write_text(content)
    assert load_state(p) == State()


def test_unknown_fields_are_ignored(tmp_path):
    p = tmp_path / "state.json"
    p.write_text('{"cam": "a", "from_a_newer_version": 1}')
    assert load_state(p) == State(cam="a")


def test_round_trip_creates_directory(tmp_path):
    p = tmp_path / "deep" / "state.json"
    s = State(on=True, cam="zug", offsets={"zug": 9}, saved={"picture-uri": "file:///a.jpg"},
              shown_key="k", shown_path="/x.jpg", frame_time="2026-11-17T13:00:00+00:00",
              fetched_at="2026-11-17T22:03:00+00:00", validator="v", last_error="e")
    save_state(p, s)
    assert load_state(p) == s


def test_save_leaves_no_temp_file_and_replaces(tmp_path):
    p = tmp_path / "state.json"
    save_state(p, State(cam="a"))
    save_state(p, State(cam="b"))
    assert [f.name for f in tmp_path.iterdir()] == ["state.json"] and load_state(p).cam == "b"


def test_paths_from_env():
    p = Paths.from_env({"HOME": "/h", "XDG_STATE_HOME": "/s"})
    assert p.state_file == Path("/s/live-wallpaper/state.json")
    assert p.lock_file == Path("/s/live-wallpaper/lock")
    assert p.cache_dir == Path("/h/.cache/live-wallpaper")


def test_paths_defaults():
    p = Paths.from_env({"HOME": "/h", "XDG_STATE_HOME": ""})
    assert p.state_file == Path("/h/.local/state/live-wallpaper/state.json")
