# SPDX-License-Identifier: Apache-2.0
import subprocess

import pytest

from live_wallpaper.desktop import KEYS, DesktopError, GSettingsDesktop


class Run:
    def __init__(self, stdout="", returncode=0, error=None, stderr=""):
        self.stdout, self.returncode, self.error, self.calls = stdout, returncode, error, []
        self.stderr = stderr

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if self.error:
            raise self.error
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


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


MEMORY_WARNING = ("(process:1): GLib-GIO-WARNING **: Using the 'memory' GSettings backend.  "
                  "Your settings will not be saved or shared with other applications.\n")


def test_memory_backend_is_an_error_not_a_silent_no_op():
    # without the dconf module gsettings exits 0 and changes nothing
    with pytest.raises(DesktopError, match="not connected"):
        GSettingsDesktop(Run(stderr=MEMORY_WARNING)).set("picture-uri", "file:///a.jpg")
    with pytest.raises(DesktopError):
        GSettingsDesktop(Run("'x'\n", stderr=MEMORY_WARNING)).get("picture-uri")
