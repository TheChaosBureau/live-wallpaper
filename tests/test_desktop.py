# SPDX-License-Identifier: Apache-2.0
import subprocess

import pytest

from live_wallpaper.desktop import KEYS, DesktopError, GSettingsDesktop


class Run:
    def __init__(self, stdout="", returncode=0, error=None):
        self.stdout, self.returncode, self.error, self.calls = stdout, returncode, error, []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if self.error:
            raise self.error
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, "boom")


def test_keys():
    assert KEYS == ("picture-uri", "picture-uri-dark", "picture-options")


def test_get_strips_quotes():
    run = Run("'file:///a.jpg'\n")
    assert GSettingsDesktop(run).get("picture-uri") == "file:///a.jpg"
    assert run.calls == [["gsettings", "get", "org.gnome.desktop.background", "picture-uri"]]


def test_get_unescapes_a_quote_in_the_value():
    assert GSettingsDesktop(Run("'file:///it\\'s.jpg'\n")).get("picture-uri") == "file:///it's.jpg"


def test_set_passes_schema_key_value():
    run = Run()
    GSettingsDesktop(run).set("picture-uri", "file:///a.jpg")
    assert run.calls == [["gsettings", "set", "org.gnome.desktop.background", "picture-uri", "file:///a.jpg"]]


def test_nonzero_exit_raises_desktop_error():
    with pytest.raises(DesktopError):
        GSettingsDesktop(Run(returncode=1)).get("picture-uri")


def test_missing_gsettings_raises_desktop_error():
    with pytest.raises(DesktopError):
        GSettingsDesktop(Run(error=FileNotFoundError("gsettings"))).set("picture-uri", "x")
