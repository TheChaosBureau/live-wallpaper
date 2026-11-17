# live-wallpaper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `live-wallpaper` command, timer and launcher entries that show a manually chosen webcam's frame (optionally time-shifted) as the GNOME wallpaper, packaged as a Nix flake with a NixOS module.

**Architecture:** A stdlib-only Python package. Pure logic (cam list, frame selection, state) is separated from the two outside-world seams, `Fetcher` (HTTP) and `Desktop` (gsettings), which tests replace with fakes. A systemd user timer calls `live-wallpaper refresh` every 5 minutes; `refresh` does nothing when cams are off.

**Tech Stack:** Python 3.11+ (stdlib only: `urllib`, `zoneinfo`, `json`, `argparse`, `fcntl`), pytest, `gsettings` (glib), `zenity`, Nix flake (`buildPythonApplication`), NixOS module, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-17-live-wallpaper-design.md`

## Global Constraints

- Runtime dependencies: Python stdlib, `glib` (for `gsettings`) and `zenity` only. No PyPI packages at runtime.
- Tests never touch the network or the real desktop settings: all fetching goes through `Fetcher`, all settings through `Desktop`.
- HTTPS only; requests go only to hosts that appear in the cam list; redirects to another host are not followed.
- A download is used only if it starts with bytes `FF D8 FF` and is at most 25 MB (`25 * 1024 * 1024`).
- User-Agent is exactly `live-wallpaper/<version>`; no personal details in any request.
- State: `$XDG_STATE_HOME/live-wallpaper/state.json` (default `~/.local/state/live-wallpaper/`). Frames: `$XDG_CACHE_HOME/live-wallpaper/` (default `~/.cache/live-wallpaper/`). User cams: `$XDG_CONFIG_HOME/live-wallpaper/cams.json`. System cams: `/etc/live-wallpaper/cams.json`.
- GNOME keys, schema `org.gnome.desktop.background`: `picture-uri`, `picture-uri-dark`, `picture-options`. The lock-screen schema is never touched.
- Offsets are whole hours, 0–23. Timer period 5 minutes. Step-back limit 6 intervals. Keep the newest 2 frames.
- A fetch failure never changes the wallpaper and never notifies; it is recorded in state as `last_error`.
- Licence Apache-2.0; every source file starts with `# SPDX-License-Identifier: Apache-2.0`.
- Commits use the repo-local git identity already configured; never pass `-c user.email`.
- One deviation from the spec's wording, same behaviour: the timer keeps ticking when cams are off and `refresh` returns immediately, instead of the timer being stopped. This survives reboots without unit state.

## Review Focus

1. **A server answers 200 with an HTML error page** (foto-webcam does this for a missing size). Expected: rejected as not a JPEG, current frame kept. Test in Task 3.
2. **The state file is empty or corrupt** (power loss mid-write). Expected: treated as "off" with no crash; writes are atomic. Test in Task 4.
3. **`use` while already on.** Expected: the saved original wallpaper is not overwritten by a cam frame, so `off` still restores the photo. Test in Task 5.
4. **The chosen cam is no longer in the cam list** (list edited, cam removed). Expected: `refresh` records a clear error and exits 0; `status` says the cam is unknown; `off` still restores. Test in Task 5.
5. **Offset across a daylight-saving change in the cam's zone.** Expected: the frame chosen is the one whose wall-clock time in the cam's zone is exactly N real hours before now. Test in Task 2.

---

## File Structure

| File | Responsibility |
|---|---|
| `flake.nix` | Package, NixOS module export, checks, dev shell |
| `pyproject.toml` | Package metadata, `live-wallpaper` entry point, pytest config |
| `src/live_wallpaper/cams.py` | Cam dataclass; load, merge and validate cam lists |
| `src/live_wallpaper/data/cams.json` | Built-in cams (NOAA GOES only) |
| `src/live_wallpaper/frames.py` | Which frame URL(s) to try for a cam, offset and time |
| `src/live_wallpaper/fetch.py` | `Fetcher` seam and the real HTTPS implementation |
| `src/live_wallpaper/state.py` | State dataclass, atomic load/save, paths |
| `src/live_wallpaper/desktop.py` | `Desktop` seam and the real `gsettings` implementation |
| `src/live_wallpaper/app.py` | The operations: use, offset, off, status, refresh |
| `src/live_wallpaper/dialogs.py` | zenity pickers |
| `src/live_wallpaper/cli.py` | Argument parsing, wiring, exit codes |
| `share/applications/*.desktop` | Three launcher entries |
| `nix/module.nix` | `programs.live-wallpaper` options, user service and timer |
| `tests/` | One test file per module, plus `tests/fakes.py` |
| `README.md`, `.github/workflows/ci.yml` | Usage, adding cams, CI |

---

### Task 1: Scaffold and cam list

**Files:**
- Create: `flake.nix`, `pyproject.toml`, `.gitignore`, `src/live_wallpaper/__init__.py`, `src/live_wallpaper/cams.py`, `src/live_wallpaper/data/cams.json`
- Test: `tests/test_cams.py`

**Interfaces:**
- Produces:
  - `__version__ = "0.1.0"` in `__init__.py`.
  - `@dataclass(frozen=True) class Cam`: `id: str`, `name: str`, `kind: str` (`"latest"` or `"foto-webcam"`), `url: str` (for `latest`: the image URL; for `foto-webcam`: the site base, e.g. `https://www.foto-webcam.eu`), `cam: str | None` (site cam id, `foto-webcam` only), `interval_minutes: int = 5` for `latest`, `10` for `foto-webcam`, `timezone: str = "Europe/Berlin"`, `size: str = "uh"`, `fit: str = "zoom"` (`"zoom"` or `"scaled"`). Property `supports_offset -> bool` (true only for `foto-webcam`). Property `host -> str`.
  - `class CamError(ValueError)`.
  - `parse_cams(raw: list[dict]) -> list[Cam]`: raises `CamError` naming the cam id and field.
  - `load_cams(paths: list[Path]) -> dict[str, Cam]`: later files override earlier by id; a missing file is skipped; insertion order kept.
  - `default_cam_paths() -> list[Path]`: built-in data file, `/etc/live-wallpaper/cams.json`, user config file.
  - `allowed_hosts(cams: dict[str, Cam]) -> frozenset[str]`.

- [ ] **Step 1: Write the flake and package skeleton.** `flake.nix` with inputs `nixpkgs` (branch `nixos-26.05`), outputs for `x86_64-linux` and `aarch64-linux`: `packages.default` (`buildPythonApplication`, `pyproject = true`, build system `setuptools`, `nativeCheckInputs = [ pytestCheckHook ]`, wrapper `PATH` prefix with `glib` and `zenity`), `devShells.default` (python3 with pytest), `checks.package = packages.default`. `pyproject.toml`: name `live-wallpaper`, version `0.1.0`, `requires-python = ">=3.11"`, script `live-wallpaper = "live_wallpaper.cli:main"`, package data `data/*.json`, pytest `testpaths = ["tests"]`, `pythonpath = ["src"]`.

- [ ] **Step 2: Write the failing tests** in `tests/test_cams.py`:

```python
def test_builtin_cams_are_noaa_only():
    cams = load_cams([default_cam_paths()[0]])
    assert cams and all(c.host == "cdn.star.nesdis.noaa.gov" for c in cams.values())
    assert all(c.kind == "latest" and c.fit == "scaled" for c in cams.values())

def test_later_file_overrides_by_id(tmp_path):
    a = write(tmp_path / "a.json", [{"id": "x", "name": "A", "kind": "latest", "url": "https://a.example/x.jpg"}])
    b = write(tmp_path / "b.json", [{"id": "x", "name": "B", "kind": "latest", "url": "https://b.example/x.jpg"}])
    assert load_cams([a, b, tmp_path / "missing.json"])["x"].name == "B"

def test_foto_webcam_defaults():
    (c,) = parse_cams([{"id": "zug", "name": "Zugspitze", "kind": "foto-webcam",
                        "url": "https://www.foto-webcam.eu", "cam": "zugspitze"}])
    assert (c.interval_minutes, c.timezone, c.size, c.supports_offset) == (10, "Europe/Berlin", "uh", True)

@pytest.mark.parametrize("bad", [
    {"id": "x", "name": "X", "kind": "latest", "url": "http://a.example/x.jpg"},   # not https
    {"id": "x", "name": "X", "kind": "rtsp", "url": "https://a.example/x"},        # unknown kind
    {"id": "x", "name": "X", "kind": "foto-webcam", "url": "https://a.example"},   # no cam
    {"id": "X y", "name": "X", "kind": "latest", "url": "https://a.example/x.jpg"},# id not [a-z0-9-]+
    {"id": "x", "name": "X", "kind": "latest", "url": "https://a.example/x.jpg", "timezone": "Mars/Base"},
    {"id": "x", "name": "X", "kind": "latest", "url": "https://a.example/x.jpg", "fit": "tile"},
])
def test_bad_cam_rejected(bad):
    with pytest.raises(CamError):
        parse_cams([bad])

def test_allowed_hosts():
    cams = {c.id: c for c in parse_cams([
        {"id": "a", "name": "A", "kind": "latest", "url": "https://a.example/x.jpg"},
        {"id": "b", "name": "B", "kind": "foto-webcam", "url": "https://www.foto-webcam.eu", "cam": "z"}])}
    assert allowed_hosts(cams) == {"a.example", "www.foto-webcam.eu"}
```

- [ ] **Step 3: Run** `nix develop -c pytest tests/test_cams.py -q`. Expected: FAIL, `live_wallpaper.cams` not importable.

- [ ] **Step 4: Implement `cams.py` and `data/cams.json`.** Built-in cams: `earth-west` ("Earth from GOES West", `https://cdn.star.nesdis.noaa.gov/GOES18/ABI/FD/GEOCOLOR/1808x1808.jpg`) and `earth-east` (GOES-19, same path with `GOES19`), both `interval_minutes: 10`, `fit: "scaled"`. Before adding `earth-east`, confirm its URL returns a JPEG with one `curl -sI`; if it does not, ship `earth-west` only.

- [ ] **Step 5: Run** `nix develop -c pytest -q` then `nix build`. Expected: all pass; build succeeds.

- [ ] **Step 6: Commit** `git add -A && git commit -m "Scaffold the package and add the cam list"`.

---

### Task 2: Frame selection

**Files:**
- Create: `src/live_wallpaper/frames.py`
- Test: `tests/test_frames.py`

**Interfaces:**
- Consumes: `Cam` from Task 1.
- Produces:
  - `@dataclass(frozen=True) class Candidate`: `url: str`, `key: str | None` (stable id of the frame, `None` when only the server knows), `frame_time: datetime | None` (aware, UTC).
  - `STEP_BACK_LIMIT = 6`.
  - `candidates(cam: Cam, offset_hours: int, now: datetime) -> list[Candidate]`: `now` must be timezone-aware. For `latest`: one candidate, `key=None`; raises `ValueError` if `offset_hours != 0`. For `foto-webcam`: `STEP_BACK_LIMIT + 1` candidates, newest first.

- [ ] **Step 1: Write the failing tests** in `tests/test_frames.py`:

```python
UTC = timezone.utc
ZUG = Cam(id="zug", name="Z", kind="foto-webcam", url="https://www.foto-webcam.eu", cam="zugspitze")

def test_latest_cam_single_candidate():
    c = Cam(id="a", name="A", kind="latest", url="https://a.example/x.jpg")
    assert candidates(c, 0, datetime(2026, 11, 17, 22, 3, tzinfo=UTC)) == [
        Candidate("https://a.example/x.jpg", None, None)]

def test_latest_cam_rejects_offset():
    c = Cam(id="a", name="A", kind="latest", url="https://a.example/x.jpg")
    with pytest.raises(ValueError):
        candidates(c, 3, datetime(2026, 11, 17, tzinfo=UTC))

def test_foto_webcam_offset_rounds_down_in_cam_zone():
    # 22:03 UTC minus 9 h = 13:03 UTC = 14:03 CET -> the 14:00 frame
    got = candidates(ZUG, 9, datetime(2026, 11, 17, 22, 3, tzinfo=UTC))
    assert got[0].url == "https://www.foto-webcam.eu/webcam/zugspitze/2026/11/17/1400_uh.jpg"
    assert got[0].key == "2026/11/17/1400"
    assert got[0].frame_time == datetime(2026, 11, 17, 13, 0, tzinfo=UTC)

def test_foto_webcam_steps_back_by_interval():
    got = candidates(ZUG, 9, datetime(2026, 11, 17, 22, 3, tzinfo=UTC))
    assert [c.key for c in got] == ["2026/11/17/1400", "2026/11/17/1350", "2026/11/17/1340",
                                    "2026/11/17/1330", "2026/11/17/1320", "2026/11/17/1310",
                                    "2026/11/17/1300"]

def test_offset_crosses_midnight():
    got = candidates(ZUG, 9, datetime(2026, 11, 17, 5, 0, tzinfo=UTC))   # 20:00 UTC on the 16th = 21:00 CET
    assert got[0].key == "2026/11/16/2100"

def test_offset_is_real_hours_across_dst_change():
    # Europe leaves summer time 2026-10-25 01:00 UTC. now = 05:00 UTC; 9 h back = 20:00 UTC on the 24th = 22:00 CEST
    got = candidates(ZUG, 9, datetime(2026, 10, 25, 5, 0, tzinfo=UTC))
    assert got[0].key == "2026/10/24/2200"

def test_interval_and_size_come_from_the_cam():
    c = dataclasses.replace(ZUG, interval_minutes=30, size="hu")
    got = candidates(c, 0, datetime(2026, 11, 17, 11, 44, tzinfo=UTC))   # 12:44 CET
    assert got[0].url.endswith("/2026/11/17/1230_hu.jpg") and got[1].key == "2026/11/17/1200"
```

- [ ] **Step 2: Run** `nix develop -c pytest tests/test_frames.py -q`. Expected: FAIL, module missing.

- [ ] **Step 3: Implement `candidates`.** Subtract the offset in UTC, convert to the cam's zone with `zoneinfo`, floor the minute to the interval, and step back in UTC so a step never lands on a wall-clock time that does not exist. URL shape: `{url}/webcam/{cam}/{YYYY}/{MM}/{DD}/{HHMM}_{size}.jpg`.

- [ ] **Step 4: Run** `nix develop -c pytest -q`. Expected: PASS.

- [ ] **Step 5: Commit** `git commit -am "Add frame selection with time offset"` (after `git add` of new files).

---

### Task 3: Fetching

**Files:**
- Create: `src/live_wallpaper/fetch.py`, `tests/fakes.py`
- Test: `tests/test_fetch.py`

**Interfaces:**
- Produces:
  - `MAX_BYTES = 25 * 1024 * 1024`, `TIMEOUT_S = 30`.
  - `@dataclass class Fetched`: `status: str` (`"ok"`, `"unchanged"`, `"missing"`), `data: bytes | None`, `validator: str | None` (the `Last-Modified` or `ETag` value to send next time).
  - `class FetchError(Exception)`: every failure other than 404 (wrong host, not HTTPS, cross-host redirect, not a JPEG, too large, network, 5xx).
  - `class Fetcher(Protocol)`: `get(self, url: str, validator: str | None = None) -> Fetched`.
  - `class HttpFetcher`: `__init__(self, allowed_hosts: frozenset[str], user_agent: str, opener=None)`; `opener` is a `urllib.request.OpenerDirector` so tests can inject one. 404 gives `status="missing"`; 304 gives `"unchanged"`.
  - `check_jpeg(data: bytes) -> None`: raises `FetchError`.
  - In `tests/fakes.py`: `class FakeFetcher`: `__init__(self, responses: dict[str, Fetched | Exception])`, records `calls: list[tuple[str, str | None]]`; an unknown URL returns `Fetched("missing", None, None)`. `JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100`.

- [ ] **Step 1: Write the failing tests** in `tests/test_fetch.py`, using a stub opener that returns canned responses (status, headers, body, final URL) without any socket:

```python
def test_ok_returns_data_and_validator():       # 200, Last-Modified: X -> Fetched("ok", JPEG, "X")
def test_sends_user_agent_and_validator():      # request has User-Agent "live-wallpaper/0.1.0" and If-Modified-Since
def test_304_is_unchanged():
def test_404_is_missing():
def test_500_raises_fetch_error():
def test_http_scheme_refused_before_any_request():      # url "http://a.example/x.jpg" -> FetchError, opener not called
def test_host_not_in_allowlist_refused_before_any_request():
def test_redirect_to_other_host_refused():      # final URL host differs -> FetchError
def test_html_body_with_200_rejected():         # body b"<html>..." -> FetchError("not a JPEG")
def test_body_over_25_mb_rejected_without_reading_it_all():   # stub yields MAX_BYTES + 1 -> FetchError
def test_network_error_becomes_fetch_error():   # opener raises URLError -> FetchError
```

Each test asserts exactly what its comment states.

- [ ] **Step 2: Run** `nix develop -c pytest tests/test_fetch.py -q`. Expected: FAIL, module missing.

- [ ] **Step 3: Implement `fetch.py`.** Use a custom `HTTPRedirectHandler` that refuses a redirect whose host differs from the request's host or whose scheme is not `https`. Read at most `MAX_BYTES + 1` bytes. An ETag validator is sent as `If-None-Match`, a date as `If-Modified-Since`.

- [ ] **Step 4: Run** `nix develop -c pytest -q`. Expected: PASS.

- [ ] **Step 5: Commit** `git commit -m "Add the HTTPS fetcher with host allowlist and JPEG check"`.

---

### Task 4: State and desktop settings

**Files:**
- Create: `src/live_wallpaper/state.py`, `src/live_wallpaper/desktop.py`
- Modify: `tests/fakes.py`
- Test: `tests/test_state.py`, `tests/test_desktop.py`

**Interfaces:**
- Produces:
  - `@dataclass class Paths`: `state_file: Path`, `cache_dir: Path`, `lock_file: Path`; `Paths.from_env(env: Mapping[str, str]) -> Paths` honouring `XDG_STATE_HOME` / `XDG_CACHE_HOME` with the defaults from Global Constraints.
  - `@dataclass class State`: `on: bool = False`, `cam: str | None = None`, `offsets: dict[str, int]`, `saved: dict[str, str] | None = None` (the three GNOME keys), `shown_key: str | None = None`, `shown_path: str | None = None`, `frame_time: str | None = None` (ISO, UTC), `fetched_at: str | None = None`, `validator: str | None = None`, `last_error: str | None = None`.
  - `load_state(path: Path) -> State`: missing, empty, corrupt or wrong-shaped file gives `State()`.
  - `save_state(path: Path, state: State) -> None`: writes a temp file in the same directory, then `os.replace`; creates the directory.
  - `KEYS = ("picture-uri", "picture-uri-dark", "picture-options")`.
  - `class Desktop(Protocol)`: `get(self, key: str) -> str`, `set(self, key: str, value: str) -> None`.
  - `class GSettingsDesktop`: runs `gsettings get|set org.gnome.desktop.background <key> [value]`; `get` strips the surrounding single quotes; a non-zero exit raises `DesktopError`.
  - `class DesktopError(Exception)`.
  - In `tests/fakes.py`: `class FakeDesktop`: `__init__(self, values: dict[str, str])`, `values` is live, `fail: bool = False` makes both methods raise `DesktopError`.

- [ ] **Step 1: Write the failing tests:**

```python
# tests/test_state.py
def test_missing_file_is_default(tmp_path):
    assert load_state(tmp_path / "nope.json") == State()

@pytest.mark.parametrize("content", ["", "{", "[]", '{"on": "yes", "offsets": 3}'])
def test_bad_file_is_default(tmp_path, content):
    p = tmp_path / "state.json"; p.write_text(content)
    assert load_state(p) == State()

def test_round_trip_creates_directory(tmp_path):
    p = tmp_path / "deep" / "state.json"
    s = State(on=True, cam="zug", offsets={"zug": 9}, saved={"picture-uri": "file:///a.jpg"})
    save_state(p, s)
    assert load_state(p) == s

def test_save_leaves_no_temp_file_and_replaces_atomically(tmp_path):
    p = tmp_path / "state.json"
    save_state(p, State(cam="a")); save_state(p, State(cam="b"))
    assert [f.name for f in tmp_path.iterdir()] == ["state.json"] and load_state(p).cam == "b"

def test_paths_from_env():
    p = Paths.from_env({"HOME": "/h", "XDG_STATE_HOME": "/s"})
    assert p.state_file == Path("/s/live-wallpaper/state.json")
    assert p.cache_dir == Path("/h/.cache/live-wallpaper")

# tests/test_desktop.py  (inject a fake `run` callable into GSettingsDesktop)
def test_get_strips_quotes():        # stdout "'file:///a.jpg'\n" -> "file:///a.jpg"
def test_set_passes_schema_key_value():   # argv == ["gsettings","set","org.gnome.desktop.background","picture-uri","file:///a.jpg"]
def test_nonzero_exit_raises_desktop_error():
```

- [ ] **Step 2: Run** `nix develop -c pytest tests/test_state.py tests/test_desktop.py -q`. Expected: FAIL, modules missing.

- [ ] **Step 3: Implement `state.py` and `desktop.py`**, and add `FakeDesktop` to `tests/fakes.py`. `GSettingsDesktop.__init__(self, run=subprocess.run)`.

- [ ] **Step 4: Run** `nix develop -c pytest -q`. Expected: PASS.

- [ ] **Step 5: Commit** `git commit -m "Add state storage and the gsettings seam"`.

---

### Task 5: Operations and command line

**Files:**
- Create: `src/live_wallpaper/app.py`, `src/live_wallpaper/cli.py`
- Test: `tests/test_app.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `Cam`, `load_cams`, `default_cam_paths`, `allowed_hosts` (Task 1); `candidates` (Task 2); `Fetcher`, `Fetched`, `FetchError`, `HttpFetcher` (Task 3); `State`, `Paths`, `load_state`, `save_state`, `Desktop`, `GSettingsDesktop`, `DesktopError`, `KEYS` (Task 4).
- Produces:
  - `class UserError(Exception)`: message is shown to the user; exit code 2.
  - `class App`: `__init__(self, cams: dict[str, Cam], paths: Paths, fetcher: Fetcher, desktop: Desktop, now: Callable[[], datetime])`.
    - `use(self, cam_id: str) -> None`
    - `set_offset(self, hours: int) -> None`
    - `off(self) -> None`
    - `refresh(self) -> None`: never raises for fetch or desktop failures.
    - `status(self) -> str`
    - `list_cams(self) -> list[Cam]`
  - `KEEP_FRAMES = 2`.
  - `main(argv: list[str] | None = None) -> int` in `cli.py`: subcommands `use <cam>`, `offset <hours>`, `off`, `status`, `list`, `refresh`, `pick`, `pick-offset` (the last two call Task 6; until then they exit 2 with "not available").

Behaviour the tests pin:
- `use`: unknown id raises `UserError` listing valid ids. When going from off to on, saves the three `KEYS` from the desktop into `state.saved`. Sets `on`, `cam`, clears `shown_key` and `validator`, then calls `refresh`.
- `set_offset`: requires cams on; hours outside 0–23 raises `UserError`; a cam without `supports_offset` raises `UserError("<name> has no archive, so it can only be shown live")`; stores per cam, clears `shown_key`, calls `refresh`.
- `refresh`: returns at once if off. Takes an exclusive non-blocking `flock` on `paths.lock_file`; if held, returns. Skips the fetch if `fetched_at` is newer than the cam's `interval_minutes` and `shown_key`/cam are unchanged. Tries candidates in order: `missing` moves to the next; `unchanged` stops; `ok` writes `cache_dir/<cam>-<UTC yyyymmddThhmmss>.jpg`, sets `picture-uri` and `picture-uri-dark` to its `file://` URI and `picture-options` to the cam's `fit`, updates state, deletes all but the newest `KEEP_FRAMES` files in `cache_dir`. A candidate whose `key` equals `shown_key` stops without fetching. Any `FetchError`, `DesktopError` or unknown cam is stored in `last_error`; success clears it.
- `off`: sets `on = False`; if `saved` is set, restores the three keys and clears `saved`. A `DesktopError` here does raise `UserError`. Frames in the cache are left in place.
- `status` lines: `Cams: on|off`, `Cam: <name> (<id>)` or `Cam: <id> (not in the cam list)`, `Offset: live|<n> hours behind`, `Frame: <local time>` when known, `Last error: <text>` when set.

- [ ] **Step 1: Write the failing tests** in `tests/test_app.py`. Fixture `app(tmp_path)` builds an `App` with two cams (`a`: `latest` at `https://a.example/x.jpg`; `zug`: the Task 2 foto-webcam cam), `FakeFetcher`, `FakeDesktop({"picture-uri": "file:///photo.jpg", "picture-uri-dark": "file:///photo-dark.jpg", "picture-options": "zoom"})`, and a settable clock starting at `2026-11-17T22:03Z`.

```python
def test_use_saves_original_and_sets_frame():
    # after use("a"): desktop picture-uri starts with "file://" + cache_dir and ends ".jpg";
    # picture-uri-dark equals picture-uri; state.saved["picture-uri"] == "file:///photo.jpg"; the file holds JPEG

def test_use_again_while_on_keeps_original_saved():          # Review Focus 3
    # use("a"); use("zug"); off() -> desktop picture-uri == "file:///photo.jpg", dark == "file:///photo-dark.jpg"

def test_off_restores_and_stops_refreshing():
    # use("a"); off(); fetcher.calls cleared; refresh() -> no calls, desktop unchanged

def test_unknown_cam_is_user_error_listing_ids():            # message contains "a" and "zug"

def test_offset_on_latest_cam_refused():                     # use("a"); set_offset(3) -> UserError "no archive"

def test_offset_range():                                     # set_offset(24) and set_offset(-1) -> UserError

def test_offset_remembered_per_cam():
    # use("zug"); set_offset(9); use("a"); use("zug") -> first URL fetched ends "/2026/11/17/1400_uh.jpg"

def test_steps_back_when_frame_missing():
    # state.offsets = {"zug": 9}; only ".../1340_uh.jpg" is in the fake; use("zug")
    # -> calls are 1400, 1350, 1340 in order; state.shown_key == "2026/11/17/1340"

def test_all_candidates_missing_keeps_frame_and_records_error():
    # use("a") ok, then use("zug") with nothing available -> picture-uri still a's frame; "no frame" in last_error

def test_same_frame_not_downloaded_twice():
    # use("zug"); clock +4 min (still the same 10-minute slot) -> refresh() makes no fetch call

def test_latest_cam_respects_interval_and_sends_validator():
    # use("a") stores validator "V1"; clock +2 min -> refresh() no call; clock +6 min -> call ("https://a.example/x.jpg", "V1")

def test_unchanged_keeps_file():                             # fake returns Fetched("unchanged") -> picture-uri unchanged

def test_fetch_error_keeps_frame_never_raises():             # fake raises FetchError -> refresh() returns; last_error set
def test_desktop_error_in_refresh_never_raises():            # desktop.fail = True -> refresh() returns; last_error set

def test_cam_removed_from_list():                            # Review Focus 4
    # state has cam "gone": refresh() returns, last_error mentions "gone"; status() contains "not in the cam list"; off() restores

def test_new_frame_gets_new_file_name_and_old_frames_pruned():
    # three successive new frames -> exactly 2 .jpg files in cache_dir, the newest is picture-uri

def test_fit_is_applied():                                   # cam with fit="scaled" -> picture-options == "scaled"

def test_refresh_returns_if_lock_held():                     # hold flock on lock_file in the test -> no fetch calls

def test_status_text():                                      # exact lines for off, on+live, on+9 hours behind
```

`tests/test_cli.py`: `main(["status"])` returns 0 and prints `Cams: off`; `main(["use", "nope"])` returns 2 and prints the message on stderr; `main(["offset", "x"])` returns 2; `main(["list"])` prints one `id<TAB>name` line per cam. `main` reads `LIVE_WALLPAPER_CAMS` (a `:`-separated path list) in place of `default_cam_paths()` when set, which is how the CLI tests avoid `/etc`.

- [ ] **Step 2: Run** `nix develop -c pytest tests/test_app.py tests/test_cli.py -q`. Expected: FAIL, modules missing.

- [ ] **Step 3: Implement `app.py` and `cli.py`.**

- [ ] **Step 4: Run** `nix develop -c pytest -q` and `nix build`. Expected: PASS; build succeeds; `./result/bin/live-wallpaper list` prints the built-in cams.

- [ ] **Step 5: Commit** `git commit -m "Add the operations and the command line"`.

---

### Task 6: Dialogs, launcher entries, NixOS module, README, CI

**Files:**
- Create: `src/live_wallpaper/dialogs.py`, `share/applications/live-wallpaper-pick.desktop`, `share/applications/live-wallpaper-offset.desktop`, `share/applications/live-wallpaper-off.desktop`, `nix/module.nix`, `nix/module-test.nix`, `README.md`, `.github/workflows/ci.yml`
- Modify: `src/live_wallpaper/cli.py`, `flake.nix`
- Test: `tests/test_dialogs.py`

**Interfaces:**
- Consumes: `App`, `UserError`, `Cam`.
- Produces:
  - `pick_cam(cams: list[Cam], current: str | None, run=subprocess.run) -> str | None`: `zenity --list --radiolist --title "Pick cam" --column "" --column id --column Cam --hide-column 2 --print-column 2`; returns the id, or `None` on cancel (exit 1).
  - `pick_offset(cam: Cam, current: int, run=subprocess.run) -> int | None`: `zenity --scale --title "Time offset" --text "<name>: hours behind live" --min-value 0 --max-value 23 --value <current>`.
  - `show_message(text: str, run=subprocess.run) -> None`: `zenity --info`.
  - CLI `pick`: calls `pick_cam` then `App.use`; `pick-offset`: if cams are off or the cam has no archive, `show_message` with the `UserError` text; else `pick_offset` then `App.set_offset`. Cancel exits 0 and changes nothing.
  - Module options: `programs.live-wallpaper.enable` (bool), `programs.live-wallpaper.package` (default: this flake's package), `programs.live-wallpaper.cams` (list of attribute sets, default `[]`, written to `/etc/live-wallpaper/cams.json`).
  - Flake outputs: `nixosModules.default`, `checks.<system>.module`.

- [ ] **Step 1: Write the failing tests** in `tests/test_dialogs.py` with a fake `run`: `pick_cam` returns the printed id and marks `current` as `TRUE`; exit code 1 returns `None`; `pick_offset` parses `"9\n"` to `9`; `main(["pick"])` with a cancelling fake changes no state and returns 0.

- [ ] **Step 2: Run** `nix develop -c pytest tests/test_dialogs.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement `dialogs.py` and wire `pick` / `pick-offset` in `cli.py`.**

- [ ] **Step 4: Add the launcher entries.** Each: `Type=Application`, `Terminal=false`, `Icon=preferences-desktop-wallpaper`, `Categories=Utility;`, `Keywords=cam;webcam;wallpaper;live;`. Names and commands: "Pick cam…" → `live-wallpaper pick`; "Set time offset…" → `live-wallpaper pick-offset`; "Back to photos" → `live-wallpaper off`. Install them to `$out/share/applications` in `flake.nix`; add `desktop-file-utils` to `nativeCheckInputs` and run `desktop-file-validate` on each in `postCheck`.

- [ ] **Step 5: Write `nix/module.nix`.** When enabled: package in `environment.systemPackages`; `environment.etc."live-wallpaper/cams.json"` from `cfg.cams` (only when non-empty); `systemd.user.services.live-wallpaper` (`Type=oneshot`, `ExecStart=<pkg>/bin/live-wallpaper refresh`, `NoNewPrivileges=true`, `Nice=19`, `TimeoutStartSec=120`); `systemd.user.timers.live-wallpaper` (`OnCalendar=*:0/5`, `Persistent=false`, `wantedBy = [ "timers.target" ]`). An assertion fails evaluation when two cams share an id.

- [ ] **Step 6: Write `nix/module-test.nix`** and expose it as `checks.<system>.module`: evaluate a minimal NixOS config with the module enabled and one extra cam, and assert (with `lib.assertMsg`, built as a trivial `runCommand`) that the timer's `OnCalendar` is `*:0/5`, the service `ExecStart` ends with `live-wallpaper refresh`, and `/etc/live-wallpaper/cams.json` parses and contains the cam id. A second evaluation with duplicate ids must fail (`builtins.tryEval`).

- [ ] **Step 7: Write `README.md`:** what it does and does not do (stills, not video; GNOME on NixOS; manual control only), install through the flake and module, the commands, how to add a cam of each kind with one worked example each, where state lives, the safety rules, and a note that users are responsible for the terms of any cam they add.

- [ ] **Step 8: Write `.github/workflows/ci.yml`:** on push and pull request, `ubuntu-latest`, check out, install Nix, run `nix flake check -L`. Pin each action to a full commit SHA with the version in a comment; `permissions: contents: read`.

- [ ] **Step 9: Run** `nix flake check -L`. Expected: `package` and `module` checks pass.

- [ ] **Step 10: Commit and push** `git commit -m "Add dialogs, launcher entries, NixOS module, README and CI"`, `git push`, then confirm the CI run is green with `gh run list -R thechaosbureau/live-wallpaper --limit 1`.

---

### Task 7: Turn it on for node-r (fleet repo) and check it live

**Files (in a fresh worktree of `/work/fleet` from `origin/main`, on a branch):**
- Modify: `flake.nix` (add the `live-wallpaper` input, pinned to the commit Task 6 pushed), `flake.lock`, `hosts/node-r.nix`

**Interfaces:**
- Consumes: `nixosModules.default` and `programs.live-wallpaper.{enable,cams}` from Task 6.

- [ ] **Step 1: Read the foto-webcam.eu usage terms** (site imprint and terms pages). If they forbid automated fetching or this kind of personal display, leave the Alpine cams out and report that. Record the finding in the pull request description.

- [ ] **Step 2: Add the input and the node-r block.** Import the module and set `programs.live-wallpaper.enable = true` with these cams: `yosemite-high-sierra` (`https://pixelcaster.com/yosemite/webcams/sentinel.jpg`), `yosemite-falls` (`.../yosfalls.jpg`), `yosemite-half-dome` (`.../ahwahnee2.jpg`), `yosemite-el-capitan` (`.../turtleback.jpg`), `huntington-beach` (`https://cdn.pixelcaster.com/public.pixelcaster.com/snapshots/hb-innocean/latest.jpg`), all `latest`; and, if Step 1 allows, `foto-webcam` cams `zugspitze`, `freiwandeck`, `funtenseetauern`, `herzogstand`, `trafoi` at `https://www.foto-webcam.eu`, each with the `captureInterval` from the site index converted to minutes.

- [ ] **Step 3: Run the fleet repo's own checks** for a host change (`nix build .#nixosConfigurations.node-r.config.system.build.toplevel --dry-run` and the repo's test entry point as its contributing notes describe). Expected: evaluation succeeds; the egress test still passes (node-r is in audit mode).

- [ ] **Step 4: Open the pull request**, wait for green, merge per the fleet repo's rules.

- [ ] **Step 5: Live check on node-r after it converges**, over ssh as the desktop user with the session bus address set: `live-wallpaper use yosemite-high-sierra`, read back `gsettings get org.gnome.desktop.background picture-uri` (a file under the cache directory), `live-wallpaper status`, `systemctl --user list-timers live-wallpaper.timer` (next run within 5 minutes), then `live-wallpaper off` and read back that `picture-uri` equals the value recorded before the check. Leave cams off; the user switches them on.
