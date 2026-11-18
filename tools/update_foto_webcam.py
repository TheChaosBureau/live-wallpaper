#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Regenerate src/live_wallpaper/data/foto-webcam.json from the site's camera index.

Run from the repo root:  nix develop -c python3 tools/update_foto_webcam.py

It fetches the index once, then asks each camera whether it has an archived
frame from noon yesterday (Central European time) at the size the app uses. That
is a headers-only request, so no picture is downloaded, one request a second.
Only the cameras that have one are kept.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from live_wallpaper import __version__  # noqa: E402
from live_wallpaper.fetch import SameHostRedirect  # noqa: E402
from live_wallpaper.foto_webcam_index import SITE, cams_from_index  # noqa: E402

INDEX = f"{SITE}/webcam/include/metadata.php"
OUT = ROOT / "src" / "live_wallpaper" / "data" / "foto-webcam.json"


def main() -> int:
    agent = f"live-wallpaper/{__version__}"
    request = urllib.request.Request(INDEX, headers={"User-Agent": agent})
    with urllib.request.urlopen(request, timeout=60) as response:
        index = json.load(response)
    cams = cams_from_index(index)
    noon = (datetime.now(ZoneInfo("Europe/Berlin")) - timedelta(days=1)).strftime("%Y/%m/%d/1200")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), SameHostRedirect())
    kept = []
    for number, cam in enumerate(cams, 1):
        url = f"{SITE}/webcam/{cam['cam']}/{noon}_uh.jpg"
        head = urllib.request.Request(url, method="HEAD", headers={"User-Agent": agent})
        try:
            with opener.open(head, timeout=30) as response:
                ok = response.status == 200 and response.headers.get_content_type() == "image/jpeg"
        except Exception:
            ok = False
        print(f"{number}/{len(cams)} {'ok  ' if ok else 'SKIP'} {cam['cam']}", flush=True)
        if ok:
            kept.append(cam)
        time.sleep(1)
    OUT.write_text(json.dumps(kept, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(kept)} of {len(cams)} cameras to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
