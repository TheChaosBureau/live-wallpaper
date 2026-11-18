# SPDX-License-Identifier: Apache-2.0
"""The settings window: browse the cams, look at each, set one as the wallpaper.

Looking at a cam changes nothing. The wallpaper changes only on "Set as
wallpaper", and the window stays open until it is closed.
"""

from __future__ import annotations

import threading

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from .app import App, UserError  # noqa: E402
from .cams import Cam, filter_cams  # noqa: E402
from .fetch import FetchError  # noqa: E402
from .preview import Preview, Previewer  # noqa: E402

APP_ID = "io.github.thechaosbureau.LiveWallpaper"
SLIDER_PAUSE_MS = 300  # dragging the slider asks for one picture, not one per step


def _hours_text(hours: int) -> str:
    return "Live" if hours == 0 else f"{hours} hour{'' if hours == 1 else 's'} behind live"


class Window(Gtk.ApplicationWindow):
    def __init__(self, app: App, previewer: Previewer, **kwargs):
        super().__init__(title="Live wallpaper", default_width=1100, default_height=680, **kwargs)
        self._app = app
        self._previewer = previewer
        self._request = 0       # the newest preview asked for; older answers are dropped
        self._slider_timer = 0
        self._busy = False
        self._rows: dict[str, Gtk.ListBoxRow] = {}
        self._marks: dict[str, Gtk.Image] = {}
        self._selected: Cam | None = None

        self.search = Gtk.SearchEntry(placeholder_text="Search cams")
        self.search.connect("search-changed", self._on_search)
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.BROWSE)
        self.listbox.set_filter_func(self._row_matches)
        self.listbox.set_placeholder(Gtk.Label(label="No cam matches.", margin_top=24))
        self.listbox.connect("row-selected", self._on_row_selected)
        for cam in app.list_cams():
            self._add_row(cam)
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(self.listbox)
        self.off_button = Gtk.Button(label="Back to photos",
                                     tooltip_text="Stop the webcam wallpaper and restore the previous one")
        self.off_button.connect("clicked", self._on_off)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, width_request=320)
        for child in (self.search, scroller, self.off_button):
            left.append(child)

        self.title_label = Gtk.Label(xalign=0, wrap=True, css_classes=["title-3"])
        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, hexpand=True, vexpand=True,
                                   can_shrink=True)
        self.spinner = Gtk.Spinner(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                                   width_request=32, height_request=32)
        stage = Gtk.Overlay(child=self.picture)
        stage.add_overlay(self.spinner)
        frame = Gtk.Frame(child=stage)
        self.frame_label = Gtk.Label(xalign=0, css_classes=["dim-label"])
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 23, 1)
        self.scale.set_hexpand(True)
        self.scale.set_round_digits(0)
        self.scale.connect("value-changed", self._on_scale)
        self.hours_label = Gtk.Label(xalign=0, width_chars=22)
        slider_row = Gtk.Box(spacing=12)
        slider_row.append(Gtk.Label(label="Time offset"))
        slider_row.append(self.scale)
        slider_row.append(self.hours_label)
        self.status_label = Gtk.Label(xalign=0, hexpand=True, wrap=True, selectable=True)
        self.set_button = Gtk.Button(label="Set as wallpaper", css_classes=["suggested-action"],
                                     sensitive=False)
        self.set_button.connect("clicked", self._on_set)
        bottom = Gtk.Box(spacing=12)
        bottom.append(self.status_label)
        bottom.append(self.set_button)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True)
        for child in (self.title_label, frame, self.frame_label, slider_row, bottom):
            right.append(child)

        root = Gtk.Box(spacing=12, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        root.append(left)
        root.append(right)
        self.set_child(root)

        self.scale.set_value(app.offset())  # (nothing is selected yet, so this asks for no picture)
        self._mark_current()
        current, _ = app.current()
        first = self._rows.get(current.id) if current else self.listbox.get_row_at_index(0)
        if first is not None:
            self.listbox.select_row(first)
            GLib.idle_add(self._scroll_to, first)
        else:
            self.title_label.set_label("No cams are configured.")
        self.search.grab_focus()

    # ---- the cam list -------------------------------------------------------

    def _add_row(self, cam: Cam) -> None:
        name = Gtk.Label(label=cam.name, xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END,
                         tooltip_text=cam.name)
        mark = Gtk.Image(icon_name="object-select-symbolic", visible=False,
                         tooltip_text="The wallpaper now")
        box = Gtk.Box(spacing=8, margin_top=6, margin_bottom=6, margin_start=8, margin_end=8)
        box.append(name)
        box.append(mark)
        row = Gtk.ListBoxRow(child=box)
        row.cam = cam
        self.listbox.append(row)
        self._rows[cam.id] = row
        self._marks[cam.id] = mark

    def _row_matches(self, row: Gtk.ListBoxRow) -> bool:
        return bool(filter_cams([row.cam], self.search.get_text()))

    def _on_search(self, _entry) -> None:
        self.listbox.invalidate_filter()

    def _scroll_to(self, row: Gtk.ListBoxRow) -> bool:
        row.grab_focus()
        self.search.grab_focus()
        return GLib.SOURCE_REMOVE

    def _mark_current(self) -> None:
        current, _ = self._app.current()
        for cam_id, mark in self._marks.items():
            mark.set_visible(current is not None and current.id == cam_id)

    def _on_row_selected(self, _listbox, row: Gtk.ListBoxRow | None) -> None:
        if row is None:
            return
        cam = self._selected = row.cam
        self.title_label.set_label(cam.name)
        # the slider keeps its value from cam to cam; only the user moves it
        self.scale.set_sensitive(cam.supports_offset)
        self._show_hours()
        self.status_label.set_label("")
        self._load_preview()

    # ---- the preview --------------------------------------------------------

    @property
    def hours(self) -> int:
        return int(round(self.scale.get_value()))

    def _show_hours(self) -> None:
        cam = self._selected
        self.hours_label.set_label(_hours_text(self.hours) if cam is None or cam.supports_offset
                                   else "Live only (no archive)")

    def _on_scale(self, _scale) -> None:
        self._show_hours()
        if self._selected is None:
            return
        if self._slider_timer:
            GLib.source_remove(self._slider_timer)
        self._slider_timer = GLib.timeout_add(SLIDER_PAUSE_MS, self._slider_settled)

    def _slider_settled(self) -> bool:
        self._slider_timer = 0
        self._load_preview()
        return GLib.SOURCE_REMOVE

    def _load_preview(self) -> None:
        if self._slider_timer:
            GLib.source_remove(self._slider_timer)
            self._slider_timer = 0
        self._request += 1
        request, cam = self._request, self._selected
        hours = self.hours if cam.supports_offset else 0
        self.spinner.start()
        self.frame_label.set_label("Loading…")
        self.set_button.set_sensitive(not self._busy)

        def work() -> None:
            try:
                result: Preview | Exception = self._previewer.get(cam, hours)
            except Exception as exc:  # shown in the window; a worker thread must not die silently
                result = exc
            GLib.idle_add(self._show_preview, request, result)

        threading.Thread(target=work, daemon=True).start()

    def _show_preview(self, request: int, result: Preview | Exception) -> bool:
        if request != self._request:
            return GLib.SOURCE_REMOVE  # the user has moved on to another cam or hour
        self.spinner.stop()
        if isinstance(result, Preview):
            try:
                self.picture.set_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(result.data)))
            except GLib.Error as exc:
                result = FetchError(f"the picture could not be shown: {exc.message}")
        if isinstance(result, Exception):
            self.picture.set_paintable(None)
            self.frame_label.set_label(f"No preview: {result}")
        elif result.frame_time is None:
            self.frame_label.set_label("Live picture")
        else:
            self.frame_label.set_label(f"Picture taken {self._app.local_time(result.frame_time)} (your time)")
        return GLib.SOURCE_REMOVE

    # ---- changing the wallpaper --------------------------------------------

    def _on_set(self, _button) -> None:
        cam, hours = self._selected, self.hours
        if cam is None:
            return

        def work() -> str:
            problem = self._app.use(cam.id, hours)
            if problem:
                return f"{cam.name} is set, but its picture could not be fetched yet: {problem}"
            return f"Wallpaper set: {cam.name}" + (
                f", {_hours_text(hours).lower()}" if hours and cam.supports_offset else "")

        self._change("Setting the wallpaper…", work)

    def _on_off(self, _button) -> None:
        def work() -> str:
            self._app.off()
            return "Cams are off. Your previous wallpaper is back."

        self._change("Restoring your wallpaper…", work)

    def _change(self, doing: str, work) -> None:
        if self._busy:
            return
        self._busy = True
        self.set_button.set_sensitive(False)
        self.off_button.set_sensitive(False)
        self.status_label.set_label(doing)

        def run() -> None:
            try:
                message = work()
            except UserError as exc:
                message = str(exc)
            except Exception as exc:
                message = f"That did not work: {exc}"
            GLib.idle_add(self._changed, message)

        threading.Thread(target=run, daemon=True).start()

    def _changed(self, message: str) -> bool:
        self._busy = False
        self.set_button.set_sensitive(self._selected is not None)
        self.off_button.set_sensitive(True)
        self.status_label.set_label(message)
        self._mark_current()
        return GLib.SOURCE_REMOVE


def run(app: App, previewer: Previewer) -> int:
    """Show the window; a second launch brings the open window to the front."""
    application = Gtk.Application(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def activate(application: Gtk.Application) -> None:
        window = application.get_active_window() or Window(app, previewer, application=application)
        window.present()

    application.connect("activate", activate)
    return application.run(None)
