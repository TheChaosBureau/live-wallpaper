# SPDX-License-Identifier: Apache-2.0
"""What the app remembers between runs, and where it keeps it."""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


@dataclass
class Paths:
    state_file: Path
    cache_dir: Path
    lock_file: Path

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Paths":
        home = env.get("HOME") or "/"
        state = Path(env.get("XDG_STATE_HOME") or os.path.join(home, ".local", "state")) / "live-wallpaper"
        cache = Path(env.get("XDG_CACHE_HOME") or os.path.join(home, ".cache")) / "live-wallpaper"
        return cls(state_file=state / "state.json", cache_dir=cache, lock_file=state / "lock")


@dataclass
class State:
    on: bool = False
    cam: str | None = None
    offsets: dict[str, int] = field(default_factory=dict)
    saved: dict[str, str] | None = None
    shown_key: str | None = None
    shown_path: str | None = None
    shown_hash: str | None = None
    frame_time: str | None = None
    fetched_at: str | None = None
    validator: str | None = None
    last_error: str | None = None


_OPTIONAL_STRINGS = ("cam", "shown_key", "shown_path", "shown_hash", "frame_time", "fetched_at", "validator", "last_error")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _from_json(raw: object) -> State:
    if not isinstance(raw, dict):
        raise ValueError("not an object")
    state = State()
    if "on" in raw:
        if not isinstance(raw["on"], bool):
            raise ValueError("on")
        state.on = raw["on"]
    for name in _OPTIONAL_STRINGS:
        value = raw.get(name)
        if value is not None and not isinstance(value, str):
            raise ValueError(name)
        setattr(state, name, value)
    offsets = raw.get("offsets", {})
    if not isinstance(offsets, dict) or not all(isinstance(k, str) and _is_int(v) for k, v in offsets.items()):
        raise ValueError("offsets")
    state.offsets = dict(offsets)
    saved = raw.get("saved")
    if saved is not None:
        if not isinstance(saved, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in saved.items()):
            raise ValueError("saved")
        state.saved = dict(saved)
    return state


def load_state(path: Path) -> State:
    """Read the state file. Anything unreadable counts as "cams off"."""
    try:
        return _from_json(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return State()


def save_state(path: Path, state: State) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dataclasses.asdict(state), handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
