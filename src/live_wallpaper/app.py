# SPDX-License-Identifier: Apache-2.0
"""The operations: pick a cam, set its offset, refresh, switch off."""

from __future__ import annotations

import fcntl
import hashlib
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator

from .cams import Cam
from .desktop import KEYS, Desktop, DesktopError
from .fetch import Fetcher, FetchError
from .frames import candidates
from .stamp import stamp as draw_credit
from .state import Paths, State, load_state, save_state

KEEP_FRAMES = 2
_INTERVAL_SLACK = timedelta(seconds=30)


# Cam ids that changed between versions: old id -> new id. A chosen cam and its
# offset follow the rename, unless the old id still names a cam.
RENAMED = {
    "alps-grossglockner": "alps-freiwandeck",
    "alps-koenigssee": "alps-funtenseetauern",
    "alps-walchensee": "alps-herzogstand",
    "alps-ortler": "alps-trafoi",
}


class UserError(Exception):
    """Something the user asked for cannot be done; the message is for them."""


class App:
    def __init__(self, cams: dict[str, Cam], paths: Paths, fetcher: Fetcher, desktop: Desktop,
                 now: Callable[[], datetime], stamp: Callable[[bytes, str], bytes] = draw_credit):
        self._stamp = stamp
        self._cams = cams
        self._paths = paths
        self._fetcher = fetcher
        self._desktop = desktop
        self._now = now

    # ---- what the user does -------------------------------------------------

    def use(self, cam_id: str, hours: int | None = None) -> str | None:
        """Show this cam, at this offset if one is given (else the one it had).

        Returns the problem if its frame could not be fetched.
        """
        if cam_id not in self._cams:
            known = ", ".join(self._cams) or "none configured"
            raise UserError(f"There is no cam called {cam_id!r}. Cams: {known}")
        cam = self._cams[cam_id]
        if hours is not None:
            if not 0 <= hours <= 23:
                raise UserError("The time offset must be a whole number of hours from 0 to 23.")
            if hours and not cam.supports_offset:
                raise UserError(f"{cam.name} has no archive, so it can only be shown live")
        with self._lock(wait=True):
            state = self._load()
            if not state.on and state.saved is None:
                state.saved = self._read_original()
            state.on = True
            state.cam = cam_id
            if hours is not None and cam.supports_offset:
                state.offsets[cam_id] = hours
            self._forget_frame(state)
            state.frame_time = None
            self._paths.cache_dir.mkdir(parents=True, exist_ok=True)
            self._save(state)  # the original wallpaper is on disk before anything changes
            self._refresh(state)
            self._save(state)
            return state.last_error

    def offset_cam(self, state: State | None = None) -> Cam:
        """The current cam, if its time offset can be set; UserError if not."""
        state = state or self._load()
        if not state.on or state.cam is None:
            raise UserError("Cams are off. Pick a cam first.")
        cam = self._cams.get(state.cam)
        if cam is None:
            raise UserError(f"The cam {state.cam!r} is not in the cam list. Pick another cam.")
        if not cam.supports_offset:
            raise UserError(f"{cam.name} has no archive, so it can only be shown live")
        return cam

    def set_offset(self, hours: int) -> str | None:
        """Set the current cam's offset. Returns the problem if no frame could be fetched."""
        with self._lock(wait=True):
            state = self._load()
            cam = self.offset_cam(state)
            if not 0 <= hours <= 23:
                raise UserError("The time offset must be a whole number of hours from 0 to 23.")
            state.offsets[cam.id] = hours
            self._forget_frame(state)
            self._refresh(state)
            self._save(state)
            return state.last_error

    def off(self) -> None:
        if not self._paths.state_file.parent.exists() and not self._paths.cache_dir.exists():
            return  # never used
        with self._lock(wait=True):
            state = self._load()
            if not state.on and state.saved is None and not self._showing_our_frame():
                return
            state.on = False
            self._forget_frame(state)
            saved, problem = state.saved, None
            if saved is None:
                problem = "Cams are off, but there is no saved wallpaper to restore. Choose one in Settings."
            else:
                try:
                    for key in KEYS:
                        if key in saved:
                            self._desktop.set(key, saved[key])
                    state.saved = None
                except DesktopError as exc:
                    problem = (f"Cams are off, but the previous wallpaper could not be restored: {exc}. "
                               "Try again.")
            self._save(state)
            if problem:
                raise UserError(problem)

    def refresh(self) -> None:
        """Called by the timer. Never raises for fetch or desktop failures."""
        if not self._load().on:
            return  # nothing to do, and nothing created for users who never use it
        with self._lock(wait=False) as held:
            if not held:
                return
            state = self._load()
            if not state.on:
                return
            self._refresh(state)
            self._save(state)

    def status(self) -> str:
        state = self._load()
        if not state.on:
            return "Cams: off"
        lines = ["Cams: on"]
        cam = self._cams.get(state.cam or "")
        if cam is None:
            lines.append(f"Cam: {state.cam} (not in the cam list)")
        else:
            lines.append(f"Cam: {cam.name} ({cam.id})")
            hours = state.offsets.get(cam.id, 0) if cam.supports_offset else 0
            if hours == 0:
                lines.append("Offset: live")
            else:
                lines.append(f"Offset: {hours} hour{'' if hours == 1 else 's'} behind")
        if state.frame_time:
            lines.append(f"Frame: {self._local(state.frame_time)}")
        if state.fetched_at:
            lines.append(f"Updated: {self._local(state.fetched_at)}")
        if state.last_error:
            lines.append(f"Last error: {state.last_error}")
        return "\n".join(lines)

    def list_cams(self) -> list[Cam]:
        return list(self._cams.values())

    def current(self) -> tuple[Cam | None, int]:
        """The chosen cam (if cams are on and it is known) and its offset."""
        state = self._load()
        cam = self._cams.get(state.cam or "") if state.on else None
        return cam, (state.offsets.get(cam.id, 0) if cam else 0)

    def offset_of(self, cam_id: str) -> int:
        """The offset this cam was last given (0 if never, or if it has no archive)."""
        cam = self._cams.get(cam_id)
        if cam is None or not cam.supports_offset:
            return 0
        return self._load().offsets.get(cam_id, 0)

    def local_time(self, when: datetime) -> str:
        return when.astimezone(self._now().tzinfo).strftime("%Y-%m-%d %H:%M")

    # ---- internals ----------------------------------------------------------

    def _load(self) -> State:
        state = load_state(self._paths.state_file)
        for old, new in RENAMED.items():
            if old in self._cams or new not in self._cams:
                continue
            if state.cam == old:
                state.cam = new
            if old in state.offsets:
                state.offsets.setdefault(new, state.offsets.pop(old))
        return state

    def _save(self, state: State) -> None:
        save_state(self._paths.state_file, state)

    @contextmanager
    def _lock(self, wait: bool) -> Iterator[bool]:
        self._paths.lock_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._paths.lock_file, "a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def _local(self, iso: str) -> str:
        try:
            when = datetime.fromisoformat(iso)
        except ValueError:
            return iso
        return when.astimezone(self._now().tzinfo).strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def _forget_frame(state: State) -> None:
        state.shown_key = None
        state.shown_path = None
        state.shown_hash = None
        state.validator = None
        state.fetched_at = None

    def _showing_our_frame(self) -> bool:
        try:
            return self._desktop.get("picture-uri").startswith(self._paths.cache_dir.as_uri())
        except DesktopError:
            return False

    def _read_original(self) -> dict[str, str] | None:
        try:
            original = {key: self._desktop.get(key) for key in KEYS}
        except DesktopError as exc:
            raise UserError(f"Could not read the current wallpaper: {exc}") from exc
        ours = self._paths.cache_dir.as_uri()
        if any(original[key].startswith(ours) for key in ("picture-uri", "picture-uri-dark")):
            return None  # the state was lost while cams were on; a cam frame is not "the original"
        return original

    def _refresh(self, state: State) -> None:
        try:
            self._refresh_or_raise(state)
        except Exception as exc:  # the timer must never fail for a fetch or desktop problem
            state.last_error = str(exc) or type(exc).__name__

    def _refresh_or_raise(self, state: State) -> None:
        cam = self._cams.get(state.cam or "")
        if cam is None:
            raise FetchError(f"the cam {state.cam!r} is not in the cam list")
        now = self._now()
        if cam.kind == "latest" and state.fetched_at:
            try:
                age = now - datetime.fromisoformat(state.fetched_at)
            except (ValueError, TypeError):  # unreadable, or written without a time zone
                age = None
            if age is not None and timedelta(0) <= age < timedelta(minutes=cam.interval_minutes) - _INTERVAL_SLACK:
                return
        offset = state.offsets.get(cam.id, 0) if cam.supports_offset else 0
        server_error = None
        for candidate in candidates(cam, offset, now):
            if candidate.key is not None and candidate.key == state.shown_key:
                state.last_error = None
                return
            try:
                fetched = self._fetcher.get(candidate.url, state.validator if candidate.key is None else None)
            except FetchError as exc:
                # An archive answers an error code for a frame it does not have
                # (foto-webcam.eu sends 502), so try the frame before it.
                if candidate.key is None or exc.status is None:
                    raise
                server_error = exc
                continue
            if fetched.status == "missing":
                continue
            raw = fetched.data or b""
            digest = hashlib.sha256(raw).hexdigest()
            if fetched.status == "ok" and not self._same_as_shown(state, digest):
                picture = self._stamp(raw, cam.credit) if cam.credit else raw
                path = self._write_frame(cam, picture, now)
                try:
                    uri = path.as_uri()
                    self._desktop.set("picture-uri", uri)
                    self._desktop.set("picture-uri-dark", uri)
                    self._desktop.set("picture-options", cam.fit)
                except BaseException:
                    # not shown, so do not keep it; whatever is shown now stays on disk
                    self._prune(self._shown_file(), drop=path)
                    raise
                state.shown_path = str(path)
                state.shown_hash = digest
                self._prune(path)
            if fetched.status == "ok":
                state.shown_key = candidate.key
                state.frame_time = candidate.frame_time.isoformat() if candidate.frame_time else None
                state.validator = fetched.validator
            state.fetched_at = now.isoformat()
            state.last_error = None
            return
        detail = f" ({server_error})" if server_error else ""
        raise FetchError(f"no frame available for {cam.name} at that time{detail}")

    def _same_as_shown(self, state: State, digest: str) -> bool:
        """True if the wallpaper already shows this very download."""
        if not state.shown_path or state.shown_hash != digest:
            return False
        try:
            shown = Path(state.shown_path)
            return shown.exists() and self._desktop.get("picture-uri") == shown.as_uri()
        except (OSError, DesktopError, ValueError):
            return False

    def _write_frame(self, cam: Cam, data: bytes, now: datetime) -> Path:
        cache = self._paths.cache_dir
        cache.mkdir(parents=True, exist_ok=True)
        stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S")
        path = cache / f"{cam.id}-{stamp}.jpg"
        counter = 1
        while path.exists():
            counter += 1
            path = cache / f"{cam.id}-{stamp}-{counter}.jpg"
        fd, tmp = tempfile.mkstemp(dir=cache, prefix=".frame-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.chmod(tmp, 0o644)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return path

    def _shown_file(self) -> Path | None:
        """The cache file the desktop is pointing at right now, if it is one of ours."""
        try:
            uri = self._desktop.get("picture-uri")
        except DesktopError:
            return None
        prefix = self._paths.cache_dir.as_uri() + "/"
        if not uri.startswith(prefix):
            return None
        return self._paths.cache_dir / Path(uri[len(prefix):]).name

    def _prune(self, current: Path | None, drop: Path | None = None) -> None:
        """Keep `current` and the newest other frames, KEEP_FRAMES in all; delete `drop`."""
        for path in ([drop] if drop else []):
            try:
                path.unlink()
            except OSError:
                pass
        if current is None:
            return
        others = sorted((p for p in self._paths.cache_dir.glob("*.jpg") if p != current),
                        key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)
        for old in others[KEEP_FRAMES - 1:]:
            try:
                old.unlink()
            except OSError:
                pass
        for stale in self._paths.cache_dir.glob(".frame-*.tmp"):
            try:
                stale.unlink()
            except OSError:
                pass
