# live-wallpaper: design

Date: 2026-11-17. Status: approved.

> Amended 2026-11-17 (owner's decision): the full cam list, including the
> foto-webcam.eu Alpine cams and the Yosemite cams, ships in this repo, with a
> credit line stamped on frames where the owner asks for one. The owners are
> contacted openly and the list follows their answers. This replaces the
> anti-goal and the "ships with NOAA only" lines below.

## Intent

Make a GNOME desktop a manually chosen window onto a real place. The user picks a
webcam and, where the cam has an archive, a time offset in hours. The cam's frame
becomes the wallpaper and keeps refreshing. Nothing else is automated.

## Goals

- Pick a cam and it stays until changed.
- Per-cam time offset in whole hours, on cams that publish an archive, so a cam in
  another time zone can follow the user's day (for example an Alpine cam 9 hours
  behind for a Pacific-time user).
- One step back to the wallpaper that was set before cams were switched on.
- Trustworthy: small, readable, no third-party code beyond tools already in nixpkgs.
- Usable by others on GNOME + NixOS as a package and a module.

## Non-goals

- Rotation between cams, daylight-aware switching, or any night handling. A dark
  frame is shown as it is.
- Time offset on cams that only publish their latest frame (would need a local
  recorder).
- Video playback. The wallpaper is a still frame.
- A preview window or a top-bar menu.
- Desktops other than GNOME, and install paths other than Nix. Forks are welcome.
- Changing the lock-screen image.

## Anti-goals

- Anything that surprises the user by changing the wallpaper on its own judgment.
- Shipping third-party cams whose terms do not clearly allow redistribution of a
  tool that points at them.

## Approaches considered

- **A. Command + timer + launcher entries (picked).** A script fetches the chosen
  cam's frame on a timer and sets the GNOME wallpaper. Launcher entries make it
  reachable from Activities search; pickers are plain GNOME dialogs. Uses only
  tools in nixpkgs and runs nothing inside the shell. Trade-off: cams are picked
  by name, not preview.
- **B. A preview window.** Same core plus a small app with thumbnails and an
  offset slider. Nicer for browsing, but a real app to write and maintain. Can be
  added later on top of A's command.
- **C. A top-bar GNOME extension.** Quickest to reach, but runs inside the shell
  and needs upkeep on each GNOME release. Ruled out.

Packaging: a standalone public repo (`thechaosbureau/live-wallpaper`, Apache-2.0)
rather than a block inside the fleet repo, because it is a general GNOME app and
not machine configuration. The fleet repo consumes it and supplies the personal
cam list.

## What the user gets

- Command `live-wallpaper`:
  - `use <cam>`: switch cams on (if off) and show this cam.
  - `offset <hours>`: set the current cam's offset (0 = live). Refused with a clear
    message on a cam without an archive.
  - `off`: stop refreshing and restore the previous wallpaper.
  - `status`: current cam, offset, time of the frame shown, on/off.
  - `list`: configured cams.
  - `pick` and `pick-offset`: the same as `use` / `offset` through a dialog.
  - `refresh`: fetch now (what the timer calls).
- Launcher entries, found by typing "cam" or "wallpaper" in Activities:
  "Pick cam…", "Set time offset…", "Back to photos".

## Behaviour

- **Cam list.** Data, not code. Each cam has an id, a display name, a kind and
  what the kind needs:
  - `latest`: one URL that always serves the newest frame. No offset.
  - `foto-webcam`: a site base URL and a cam id. Latest and archived frames are
    fetched by timestamp; offset is supported. The capture interval comes from the
    cam entry (default 10 minutes).
  The package ships with NOAA GOES Earth imagery only. Users add cams through the
  module option or a file in `~/.config/live-wallpaper/`.
- **Refresh.** A systemd user timer runs `refresh` every 5 minutes while cams are
  on. A cam is not fetched more often than its own interval, and an unchanged
  frame is not downloaded again.
- **Offset.** Target time = now minus the offset, expressed in the cam's own time
  zone, rounded down to the cam's capture interval. If that frame does not exist,
  step back one interval at a time, up to a small limit, then keep the current
  frame. The offset is remembered per cam.
- **Setting the wallpaper.** Each new frame is written under a new file name
  (GNOME does not notice a file changed in place), then `picture-uri` and
  `picture-uri-dark` are pointed at it and `picture-options` set to `zoom`. Old
  frames are deleted, keeping the newest two.
- **Switching on.** The current `picture-uri`, `picture-uri-dark` and
  `picture-options` are saved once, when going from off to on.
- **Switching off.** The timer stops and the saved values are restored.
- **Failures.** If a fetch fails (offline, server error, bad file), the current
  frame stays and nothing is shown to the user. `status` reports the last error.
- **State** lives in `~/.local/state/live-wallpaper/` and frames in
  `~/.cache/live-wallpaper/`.

## Safety

- HTTPS only, and only to hosts that appear in the cam list. Redirects to other
  hosts are not followed.
- A download is used only if it starts with the JPEG signature and is under a size
  cap (25 MB).
- Runs as the user, with no extra privileges. The systemd unit is hardened as far
  as a user unit that must talk to the session's settings service allows.
- Requests carry a generic client name and no personal details.

## Constraints

- GNOME on Wayland, NixOS 26.05, as the tested target.
- Tests never touch the network: fetching is behind a seam the tests replace.
- No manual acceptance step for the user. Everything is checked by automated
  tests; the live check on the first machine is done by the builder.

## Left to the builder

- Implementation language for the script (shell or Python), state file format,
  exact dialog wording, and unit hardening flags.
- The exact GOES products shipped by default.

## Open items

- Read the foto-webcam.eu usage terms before the personal cam list that uses it
  is merged in the fleet repo; drop those cams if the terms forbid this use.
- Older foto-webcam archive frames at the 4K size failed on the two dates tried;
  does not affect offsets of hours.
