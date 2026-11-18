# SPDX-License-Identifier: Apache-2.0
"""The pickers, shown with zenity."""

from __future__ import annotations

import subprocess
from xml.sax.saxutils import escape

from .cams import Cam


class DialogError(Exception):
    """A dialog could not be shown."""


def _zenity(args: list[str], run) -> str | None:
    """Run zenity; return what it printed, or None if the user cancelled."""
    try:
        done = run(["zenity", *args], capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise DialogError(f"could not show a dialog: {exc}") from exc
    if done.returncode != 0:
        return None
    return (done.stdout or "").strip()


def pick_cam(cams: list[Cam], current: str | None, run=subprocess.run) -> str | None:
    args = ["--list", "--radiolist", "--title=Pick cam", "--text=Show this cam as the wallpaper:",
            "--width=420", "--height=480",
            "--column=", "--column=id", "--column=Cam", "--hide-column=2", "--print-column=2"]
    for cam in cams:
        args += ["TRUE" if cam.id == current else "FALSE", cam.id, cam.name]
    chosen = _zenity(args, run)
    return chosen if chosen in {cam.id for cam in cams} else None


def pick_offset(cam: Cam, current: int, run=subprocess.run) -> int | None:
    answer = _zenity(["--scale", "--title=Time offset", f"--text={escape(cam.name)}: hours behind live",
                      "--min-value=0", "--max-value=23", f"--value={current}", "--step=1"], run)
    try:
        return int(answer) if answer is not None else None
    except ValueError:
        return None


def show_message(text: str, run=subprocess.run) -> None:
    _zenity(["--info", "--no-markup", "--title=Live wallpaper", f"--text={text}"], run)


LONG_LIST = 40


def filter_cams(cams: list[Cam], text: str) -> list[Cam]:
    """Cams whose name or id contains every word of `text` (any case)."""
    words = text.casefold().split()
    return [cam for cam in cams
            if all(word in f"{cam.name} {cam.id}".casefold() for word in words)]


def ask_filter(count: int, run=subprocess.run) -> str | None:
    return _zenity(["--entry", "--title=Pick cam",
                    f"--text=There are {count} cams. Type part of a name to narrow the list "
                    "(a place, a mountain, a country), or leave it empty to see them all."], run)


def choose_cam(cams: list[Cam], current: str | None, run=subprocess.run) -> str | None:
    """The whole picking flow: a name filter first when the list is long."""
    if len(cams) > LONG_LIST:
        text = ask_filter(len(cams), run)
        if text is None:
            return None
        matches = filter_cams(cams, text)
        if not matches:
            show_message(f"No cam matches \"{text}\".", run)
            return None
        cams = matches
    return pick_cam(cams, current, run)
