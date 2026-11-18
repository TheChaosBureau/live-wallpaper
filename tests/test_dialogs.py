# SPDX-License-Identifier: Apache-2.0
import json
import subprocess

import pytest

from live_wallpaper import cli, dialogs
from live_wallpaper.cams import parse_cams
from live_wallpaper.state import State, load_state, save_state

CAMS = parse_cams([
    {"id": "a", "name": "Cam A", "kind": "latest", "url": "https://a.example/x.jpg"},
    {"id": "zug", "name": "Zugspitze", "kind": "foto-webcam", "url": "https://www.foto-webcam.eu",
     "cam": "zugspitze"}])


class Run:
    def __init__(self, stdout="", returncode=0, error=None):
        self.stdout, self.returncode, self.error, self.calls = stdout, returncode, error, []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if self.error:
            raise self.error
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, "")


def test_pick_cam_returns_the_printed_id_and_marks_current():
    run = Run("zug\n")
    assert dialogs.pick_cam(CAMS, "zug", run) == "zug"
    (argv,) = run.calls
    assert argv[:3] == ["zenity", "--list", "--radiolist"]
    assert "--print-column=2" in argv and "--hide-column=2" in argv
    assert argv[-6:] == ["FALSE", "a", "Cam A", "TRUE", "zug", "Zugspitze"]


def test_pick_cam_cancel_returns_none():
    assert dialogs.pick_cam(CAMS, None, Run(returncode=1)) is None


def test_pick_cam_ignores_an_id_that_is_not_a_cam():
    assert dialogs.pick_cam(CAMS, None, Run("bogus\n")) is None


def test_pick_offset_parses_hours():
    run = Run("9\n")
    assert dialogs.pick_offset(CAMS[1], 3, run) == 9
    (argv,) = run.calls
    assert argv[:2] == ["zenity", "--scale"]
    assert {"--min-value=0", "--max-value=23", "--value=3"} <= set(argv)


def test_pick_offset_cancel_returns_none():
    assert dialogs.pick_offset(CAMS[1], 0, Run(returncode=1)) is None


def test_missing_zenity_is_a_dialog_error():
    with pytest.raises(dialogs.DialogError):
        dialogs.pick_cam(CAMS, None, Run(error=FileNotFoundError("zenity")))


@pytest.fixture
def env(tmp_path, monkeypatch):
    cams = tmp_path / "cams.json"
    cams.write_text(json.dumps([
        {"id": "a", "name": "Cam A", "kind": "latest", "url": "https://a.example/x.jpg"}]))
    monkeypatch.setenv("LIVE_WALLPAPER_CAMS", str(cams))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return tmp_path


def test_cli_pick_cancel_changes_nothing(env, monkeypatch):
    monkeypatch.setattr(dialogs, "choose_cam", lambda cams, current: None)
    assert cli.main(["pick"]) == 0
    assert load_state(env / "state" / "live-wallpaper" / "state.json") == State()


def test_cli_pick_offset_when_off_shows_a_message(env, monkeypatch):
    shown = []
    monkeypatch.setattr(dialogs, "show_message", shown.append)
    assert cli.main(["pick-offset"]) == 0
    assert shown == ["Cams are off. Pick a cam first."]


def test_cli_pick_offset_on_a_cam_without_archive_shows_a_message(env, monkeypatch):
    save_state(env / "state" / "live-wallpaper" / "state.json", State(on=True, cam="a"))
    shown = []
    monkeypatch.setattr(dialogs, "show_message", shown.append)
    monkeypatch.setattr(dialogs, "pick_offset", lambda cam, current: pytest.fail("must not ask"))
    assert cli.main(["pick-offset"]) == 0
    assert shown == ["Cam A has no archive, so it can only be shown live"]


def test_messages_are_not_parsed_as_markup():
    run = Run()
    dialogs.show_message("Zell & Kaprun <down>", run)
    assert "--no-markup" in run.calls[0] and "--text=Zell & Kaprun <down>" in run.calls[0]


def test_cam_name_is_escaped_in_the_offset_dialog():
    (cam,) = parse_cams([{"id": "z", "name": "Zell & Kaprun", "kind": "foto-webcam",
                          "url": "https://www.foto-webcam.eu", "cam": "z"}])
    run = Run("3\n")
    dialogs.pick_offset(cam, 0, run)
    assert "--text=Zell &amp; Kaprun: hours behind live" in run.calls[0]


def test_filter_cams_matches_any_word_case_insensitively_in_name_or_id():
    from live_wallpaper.dialogs import filter_cams
    assert [c.id for c in filter_cams(CAMS, "ZUG")] == ["zug"]
    assert [c.id for c in filter_cams(CAMS, "cam a")] == ["a"]
    assert [c.id for c in filter_cams(CAMS, "  ")] == ["a", "zug"]
    assert filter_cams(CAMS, "nothing-like-this") == []


def test_ask_filter_returns_text_or_none_on_cancel():
    run = Run("glock\n")
    assert dialogs.ask_filter(300, run) == "glock"
    assert run.calls[0][:2] == ["zenity", "--entry"]
    assert dialogs.ask_filter(300, Run(returncode=1)) is None


def many_cams(n):
    return parse_cams([{"id": f"c{i}", "name": f"Cam {i}", "kind": "latest", "url": "https://a.example/x.jpg"}
                       for i in range(n)])


def test_choose_cam_asks_for_a_filter_only_when_the_list_is_long(monkeypatch):
    asked = []
    monkeypatch.setattr(dialogs, "ask_filter", lambda count, run=None: asked.append(count) or "cam 79")
    monkeypatch.setattr(dialogs, "pick_cam", lambda cams, current, run=None: [c.id for c in cams])
    assert dialogs.choose_cam(CAMS, None) == ["a", "zug"] and asked == []
    assert dialogs.choose_cam(many_cams(80), None) == ["c79"] and asked == [80]


def test_choose_cam_cancel_at_the_filter_changes_nothing(monkeypatch):
    monkeypatch.setattr(dialogs, "ask_filter", lambda count, run=None: None)
    monkeypatch.setattr(dialogs, "pick_cam", lambda *a, **k: pytest.fail("must not show the list"))
    assert dialogs.choose_cam(many_cams(80), None) is None


def test_choose_cam_tells_the_user_when_nothing_matches(monkeypatch):
    said = []
    monkeypatch.setattr(dialogs, "ask_filter", lambda count, run=None: "zzz")
    monkeypatch.setattr(dialogs, "show_message", lambda text, run=None: said.append(text))
    monkeypatch.setattr(dialogs, "pick_cam", lambda *a, **k: pytest.fail("must not show the list"))
    assert dialogs.choose_cam(many_cams(80), None) is None and "zzz" in said[0]
