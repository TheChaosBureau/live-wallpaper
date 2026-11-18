# live-wallpaper

Put a real place on your GNOME desktop. Pick a webcam, optionally time-shift it,
and its latest frame becomes your wallpaper and keeps refreshing.

- **Stills, not video.** The wallpaper is the cam's newest still frame, fetched
  every few minutes. Nothing decodes video in the background.
- **Manual control only.** You choose the cam and its time offset. It never
  rotates cams or swaps the wallpaper on its own judgment. A cam that is dark at
  night is shown dark.
- **Small and readable.** Python standard library, plus `gsettings`, `zenity`
  and Pillow (used only to draw a credit line on cams that ask for one).

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

The package ships with these cams:

| Cams | From | Notes |
|---|---|---|
| `earth-west`, `earth-east` | NOAA GOES satellites | US government works, public domain |
| `yosemite-high-sierra`, `yosemite-falls`, `yosemite-half-dome`, `yosemite-el-capitan`, `yosemite-wawona-dome` | [Yosemite Conservancy](https://yosemite.org/webcams/) | Shown whole, never cropped; each frame carries the Conservancy's logo |
| `huntington-beach` | Huntington Beach pier, hosted by Pixelcaster | |
| `alps-…` (286 cams, for example `alps-zugspitze`) | [foto-webcam.eu](https://www.foto-webcam.eu/) | Every running camera of the site's own. Shown whole with a `www.foto-webcam.eu` credit on every frame; these support a time offset |

The pictures belong to the people who run the cameras, not to this project. If
you run one of these cameras and would like it shown differently, credited
differently, or removed, please open an issue and it will be changed.

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

### Credit: foto-webcam.eu

The `foto-webcam` kind exists because of [foto-webcam.eu](https://www.foto-webcam.eu/),
a volunteer-run network of several hundred Alpine cameras whose pictures are in a
different league from ordinary webcams. The images are theirs: their copyright,
their terms. Those terms ask for a visible source credit and forbid cropping or
stretching, so cams from that site should carry their name and show the whole image:

```nix
{
  id = "zugspitze"; name = "Zugspitze"; kind = "foto-webcam";
  url = "https://www.foto-webcam.eu"; cam = "zugspitze";
  credit = "www.foto-webcam.eu";   # stamped on every frame
  fit = "scaled";                  # whole image, never cropped
}
```

This project is not affiliated with foto-webcam.eu. It ships the site's own
running cameras, each set up exactly as above, and its operators have been asked
whether that is all right with them; the list will follow their answer. The list
is a snapshot made by `tools/update_foto_webcam.py`, which reads the site's public
camera index and checks each camera once without downloading any picture. And
visit the site itself: the archive and the full-size pictures there are worth it.

With this many cams, "Pick cam…" first asks for part of a name (a place, a
mountain, a country) and then shows the matches.

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
| `credit` | One short line stamped small in the bottom-right corner of the frame | none |

## Safety

- HTTPS only, and only to hosts that appear in your cam list. Redirects to any
  other host are refused.
- A download is used only if it is a JPEG and at most 25 MB.
- It runs as you, with no extra privileges, and sends a generic client name
  (`live-wallpaper/<version>`) and nothing about you. Proxy settings in the
  environment are ignored.
- The timer's job runs sandboxed: the system and your home directory are
  read-only to it, except its own cache and state directories. The sandbox
  paths assume the default XDG locations.
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
