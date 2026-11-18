# SPDX-License-Identifier: Apache-2.0
import json

import pytest

from live_wallpaper.cams import (
    CamError,
    allowed_hosts,
    default_cam_paths,
    load_cams,
    parse_cams,
)


def write(path, cams):
    path.write_text(json.dumps(cams))
    return path


def test_builtin_cams_are_noaa_only():
    cams = load_cams([default_cam_paths()[0]])
    assert cams and all(c.host == "cdn.star.nesdis.noaa.gov" for c in cams.values())
    assert all(c.kind == "latest" and c.fit == "scaled" for c in cams.values())


def test_later_file_overrides_by_id(tmp_path):
    a = write(tmp_path / "a.json", [{"id": "x", "name": "A", "kind": "latest", "url": "https://a.example/x.jpg"}])
    b = write(tmp_path / "b.json", [{"id": "x", "name": "B", "kind": "latest", "url": "https://b.example/x.jpg"}])
    assert load_cams([a, b, tmp_path / "missing.json"])["x"].name == "B"


def test_latest_defaults():
    (c,) = parse_cams([{"id": "a", "name": "A", "kind": "latest", "url": "https://a.example/x.jpg"}])
    assert (c.interval_minutes, c.fit, c.supports_offset) == (5, "zoom", False)


def test_foto_webcam_defaults():
    (c,) = parse_cams([{"id": "zug", "name": "Zugspitze", "kind": "foto-webcam",
                        "url": "https://www.foto-webcam.eu", "cam": "zugspitze"}])
    assert (c.interval_minutes, c.timezone, c.size, c.supports_offset) == (10, "Europe/Berlin", "uh", True)


@pytest.mark.parametrize("bad", [
    {"id": "x", "name": "X", "kind": "latest", "url": "http://a.example/x.jpg"},
    {"id": "x", "name": "X", "kind": "rtsp", "url": "https://a.example/x"},
    {"id": "x", "name": "X", "kind": "foto-webcam", "url": "https://a.example"},
    {"id": "X y", "name": "X", "kind": "latest", "url": "https://a.example/x.jpg"},
    {"id": "x", "name": "X", "kind": "latest", "url": "https://a.example/x.jpg", "timezone": "Mars/Base"},
    {"id": "x", "name": "X", "kind": "latest", "url": "https://a.example/x.jpg", "fit": "tile"},
    {"id": "x", "kind": "latest", "url": "https://a.example/x.jpg"},
    {"id": "x", "name": "X", "kind": "latest", "url": "https://a.example/x.jpg", "interval_minutes": 0},
    {"id": "x", "name": "X", "kind": "latest", "url": "https://a.example/x.jpg", "colour": "red"},
    "not a dict",
])
def test_bad_cam_rejected(bad):
    with pytest.raises(CamError):
        parse_cams([bad])


def test_file_that_is_not_a_list_rejected(tmp_path):
    p = tmp_path / "c.json"
    p.write_text('{"id": "x"}')
    with pytest.raises(CamError):
        load_cams([p])


def test_broken_json_rejected(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("[")
    with pytest.raises(CamError):
        load_cams([p])


def test_allowed_hosts():
    cams = {c.id: c for c in parse_cams([
        {"id": "a", "name": "A", "kind": "latest", "url": "https://a.example/x.jpg"},
        {"id": "b", "name": "B", "kind": "foto-webcam", "url": "https://www.foto-webcam.eu", "cam": "z"}])}
    assert allowed_hosts(cams) == {"a.example", "www.foto-webcam.eu"}


def test_credit_is_optional_text():
    plain, credited = parse_cams([
        {"id": "a", "name": "A", "kind": "latest", "url": "https://a.example/x.jpg"},
        {"id": "b", "name": "B", "kind": "latest", "url": "https://a.example/y.jpg", "credit": "www.example.org"}])
    assert plain.credit is None and credited.credit == "www.example.org"


@pytest.mark.parametrize("credit", ["", "   ", 7, "x" * 81, "two\nlines"])
def test_bad_credit_rejected(credit):
    with pytest.raises(CamError):
        parse_cams([{"id": "a", "name": "A", "kind": "latest", "url": "https://a.example/x.jpg", "credit": credit}])
