# SPDX-License-Identifier: Apache-2.0
import json

import pytest

from live_wallpaper.cli import main


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    cams = tmp_path / "cams.json"
    cams.write_text(json.dumps([
        {"id": "a", "name": "Cam A", "kind": "latest", "url": "https://a.example/x.jpg"},
        {"id": "zug", "name": "Zugspitze", "kind": "foto-webcam", "url": "https://www.foto-webcam.eu",
         "cam": "zugspitze"}]))
    monkeypatch.setenv("LIVE_WALLPAPER_CAMS", str(cams))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return tmp_path


def test_status_when_off(capsys):
    assert main(["status"]) == 0
    assert capsys.readouterr().out == "Cams: off\n"


def test_list(capsys):
    assert main(["list"]) == 0
    assert capsys.readouterr().out == "a\tCam A\nzug\tZugspitze\n"


def test_unknown_cam_exits_2_with_message_on_stderr(capsys):
    assert main(["use", "nope"]) == 2
    out = capsys.readouterr()
    assert "nope" in out.err and out.out == ""


def test_offset_needs_a_number(capsys):
    assert main(["offset", "x"]) == 2


def test_no_command_exits_2(capsys):
    assert main([]) == 2


def test_refresh_when_off_exits_0(capsys):
    assert main(["refresh"]) == 0


def test_broken_cam_list_exits_2(env, capsys):
    (env / "cams.json").write_text("[")
    assert main(["status"]) == 2
    assert "cams.json" in capsys.readouterr().err


def test_off_works_with_a_broken_cam_list(env, capsys):
    (env / "cams.json").write_text("[")
    assert main(["off"]) == 0


def test_use_reports_a_frame_that_could_not_be_fetched(monkeypatch, capsys):
    class Stub:
        def use(self, cam, hours=None):
            return "could not reach a.example"

    from live_wallpaper import cli
    monkeypatch.setattr(cli, "_build_app", lambda **kw: Stub())
    assert main(["use", "a"]) == 1
    assert "could not reach a.example" in capsys.readouterr().err


def test_refresh_never_prints_a_traceback(monkeypatch, capsys):
    class Stub:
        def refresh(self):
            raise OSError("disk full")

    from live_wallpaper import cli
    monkeypatch.setattr(cli, "_build_app", lambda **kw: Stub())
    assert main(["refresh"]) == 1
    assert capsys.readouterr().err == "live-wallpaper: disk full\n"
