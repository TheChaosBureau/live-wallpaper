# SPDX-License-Identifier: Apache-2.0
"""The live-wallpaper command."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .app import App, UserError
from .cams import CamError, allowed_hosts, default_cam_paths, load_cams
from .desktop import GSettingsDesktop
from .fetch import HttpFetcher
from .state import Paths


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="live-wallpaper",
        description="Show a webcam's latest frame as the GNOME wallpaper.")
    parser.add_argument("--version", action="version", version=f"live-wallpaper {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")
    use = sub.add_parser("use", help="switch cams on and show this cam")
    use.add_argument("cam")
    offset = sub.add_parser("offset", help="show the current cam this many hours behind (0 = live)")
    offset.add_argument("hours", type=int)
    sub.add_parser("off", help="stop and restore the previous wallpaper")
    sub.add_parser("status", help="show the current cam, offset and frame time")
    sub.add_parser("list", help="list the configured cams")
    sub.add_parser("refresh", help="fetch the current cam's frame now (what the timer runs)")
    sub.add_parser("pick", help="pick a cam in a dialog")
    sub.add_parser("pick-offset", help="set the time offset in a dialog")
    return parser


def _build_app() -> App:
    override = os.environ.get("LIVE_WALLPAPER_CAMS")
    paths = [Path(p) for p in override.split(":") if p] if override else default_cam_paths()
    cams = load_cams(paths)
    return App(
        cams=cams,
        paths=Paths.from_env(os.environ),
        fetcher=HttpFetcher(allowed_hosts(cams), f"live-wallpaper/{__version__}"),
        desktop=GSettingsDesktop(),
        now=lambda: datetime.now().astimezone(),
    )


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    try:
        app = _build_app()
        if args.command == "use":
            app.use(args.cam)
        elif args.command == "offset":
            app.set_offset(args.hours)
        elif args.command == "off":
            app.off()
        elif args.command == "status":
            print(app.status())
        elif args.command == "list":
            for cam in app.list_cams():
                print(f"{cam.id}\t{cam.name}")
        elif args.command == "refresh":
            app.refresh()
        else:
            raise UserError(f"{args.command} is not available yet")
    except (UserError, CamError) as exc:
        print(f"live-wallpaper: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
