# live-wallpaper

Put a real place on your GNOME desktop. Pick a webcam, optionally time-shift it,
and its latest frame becomes your wallpaper and keeps refreshing.

- **Stills, not video.** The wallpaper is the cam's newest still frame, fetched
  every few minutes. Nothing decodes video in the background.
- **Manual control only.** You choose the cam and its time offset. It never
  rotates cams or swaps the wallpaper on its own judgment. A cam that is dark at
  night is shown dark.
- **Small and readable.** Python standard library only, plus `gsettings` and
  `zenity`.

Tested on GNOME (Wayland) on NixOS 26.05. Other desktops and other install paths
are not supported; forks are welcome.

## Install (NixOS, flakes)

```nix
{
  inputs.live-wallpaper.url = "github:TheChaosBureau/live-wallpaper";

  outputs = { nixpkgs, live-wallpaper, ... }: {
    nixosConfigurations.my-host = nixpkgs.lib.nixosSystem {
      modules = [
        live-wallpaper.nixosModules.default
        {
          programs.live-wallpaper.enable = true;
          programs.live-wallpaper.cams = [
            { id = "my-cam"; name = "My cam"; kind = "latest"; url = "https://example.org/cam.jpg"; }
          ];
        }
      ];
    };
  };
}
```

This installs the `live-wallpaper` command, three launcher entries, and a user
timer that refreshes the wallpaper every 5 minutes while cams are on.

## Use

Press Super and type "cam":

- **Pick cam…** chooses a cam and switches cams on.
- **Set time offset…** shows the current cam some hours behind live.
- **Back to photos** stops and restores the wallpaper you had before.

Or from a terminal:

```
live-wallpaper list            # the cams you can pick
live-wallpaper use earth-west  # switch cams on and show this cam
live-wallpaper offset 9        # show the current cam 9 hours behind (0 = live)
live-wallpaper status          # cam, offset, frame time, last error
live-wallpaper off             # stop and restore the previous wallpaper
```

## Cams

The package ships with two cams, both NOAA GOES satellite views of Earth
(`earth-west`, `earth-east`), which are US government works in the public domain.

Add your own through `programs.live-wallpaper.cams`, or in
`~/.config/live-wallpaper/cams.json` (a JSON list with the same fields). A cam
with the same `id` as an earlier one replaces it. **You are responsible for the
terms of use of any cam you add.**

### `latest`: a URL that always serves the newest frame

```nix
{ id = "harbour"; name = "Harbour"; kind = "latest"; url = "https://example.org/harbour/latest.jpg"; }
```

A `latest` cam can only be shown live.

### `foto-webcam`: a site that keeps an archive by date and time

For sites running the foto-webcam software, which publish every frame at
`<url>/webcam/<cam>/YYYY/MM/DD/HHMM_<size>.jpg`:

```nix
{
  id = "summit"; name = "Summit"; kind = "foto-webcam";
  url = "https://www.example.org"; cam = "summit";
  interval_minutes = 10;         # how often the cam takes a frame
  timezone = "Europe/Berlin";    # the zone the site's file names use
}
```

These cams support a time offset. With an offset of 9 hours, a cam nine time
zones east of you follows your day: its sunrise arrives with yours.

### Fields

| Field | Meaning | Default |
|---|---|---|
| `id` | Lower-case letters, digits and dashes | required |
| `name` | Shown in the picker | required |
| `kind` | `latest` or `foto-webcam` | required |
| `url` | `https://` image URL (`latest`) or site address (`foto-webcam`) | required |
| `cam` | The site's own cam id (`foto-webcam` only) | required for `foto-webcam` |
| `interval_minutes` | Do not fetch more often than this | 5 (`latest`), 10 (`foto-webcam`) |
| `timezone` | Zone of the archive's file names | `Europe/Berlin` |
| `size` | Archive size suffix | `uh` (3840×2160) |
| `fit` | `zoom` fills the screen, `scaled` shows the whole image | `zoom` |

## Safety

- HTTPS only, and only to hosts that appear in your cam list. Redirects to any
  other host are refused.
- A download is used only if it is a JPEG and at most 25 MB.
- It runs as you, with no extra privileges, and sends a generic client name
  (`live-wallpaper/<version>`) and nothing about you.
- If a fetch fails, the current frame stays and nothing pops up; `status` shows
  the last error.
- The lock-screen image is never touched.

## Where things live

| What | Where |
|---|---|
| State (cam, offsets, saved wallpaper) | `~/.local/state/live-wallpaper/state.json` |
| Frames (the newest two) | `~/.cache/live-wallpaper/` |
| Your cams | `~/.config/live-wallpaper/cams.json` |
| System cams (from the module) | `/etc/live-wallpaper/cams.json` |

## Development

```
nix develop -c pytest -q   # tests; they never touch the network or your settings
nix flake check -L         # package build, tests and the module check
```

## Licence

Apache-2.0. See [LICENSE](LICENSE).
