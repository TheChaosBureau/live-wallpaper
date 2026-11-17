# SPDX-License-Identifier: Apache-2.0
"""The pickers, shown with zenity."""

from __future__ import annotations

import subprocess

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
    answer = _zenity(["--scale", "--title=Time offset", f"--text={cam.name}: hours behind live",
                      "--min-value=0", "--max-value=23", f"--value={current}", "--step=1"], run)
    try:
        return int(answer) if answer is not None else None
    except ValueError:
        return None


def show_message(text: str, run=subprocess.run) -> None:
    _zenity(["--info", "--title=Live wallpaper", f"--text={text}"], run)
