# SPDX-License-Identifier: Apache-2.0
"""Reading and setting the GNOME wallpaper."""

from __future__ import annotations

import ast
import subprocess
from typing import Protocol

SCHEMA = "org.gnome.desktop.background"
KEYS = ("picture-uri", "picture-uri-dark", "picture-options")


class DesktopError(Exception):
    """The desktop settings could not be read or changed."""


class Desktop(Protocol):
    def get(self, key: str) -> str: ...
    def set(self, key: str, value: str) -> None: ...


def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] in "'\"" and text[-1] == text[0]:
        try:
            value = ast.literal_eval(text)
            if isinstance(value, str):
                return value
        except (ValueError, SyntaxError):
            pass
        return text[1:-1]
    return text


class GSettingsDesktop:
    def __init__(self, run=subprocess.run):
        self._run = run

    def _gsettings(self, *args: str) -> str:
        argv = ["gsettings", *args]
        try:
            done = self._run(argv, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError) as exc:
            raise DesktopError(f"could not run gsettings: {exc}") from exc
        if done.returncode != 0:
            raise DesktopError(f"gsettings failed: {(done.stderr or '').strip() or done.returncode}")
        if "'memory' GSettings backend" in (done.stderr or ""):
            # gsettings exits 0 here but nothing reaches the desktop
            raise DesktopError("gsettings is not connected to the desktop settings (no dconf backend)")
        return done.stdout or ""

    def get(self, key: str) -> str:
        return _unquote(self._gsettings("get", SCHEMA, key))

    def set(self, key: str, value: str) -> None:
        self._gsettings("set", SCHEMA, key, value)
