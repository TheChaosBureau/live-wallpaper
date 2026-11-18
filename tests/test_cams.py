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


def builtin():
    return load_cams([default_cam_paths()[0]])


def test_builtin_cams_load_and_have_unique_ids():
    import json
    raw = json.loads(default_cam_paths()[0].read_text(encoding="utf-8"))
    cams = builtin()
    assert len(cams) == len(raw) == 13
    assert {"earth-west", "yosemite-high-sierra", "huntington-beach", "alps-zugspitze"} <= set(cams)


def test_builtin_hosts_are_the_expected_ones():
    assert allowed_hosts(builtin()) == {
        "cdn.star.nesdis.noaa.gov", "pixelcaster.com", "cdn.pixelcaster.com", "www.foto-webcam.eu"}


def test_foto_webcam_eu_cams_carry_its_credit_and_are_never_cropped():
    theirs = [c for c in builtin().values() if c.host == "www.foto-webcam.eu"]
    assert len(theirs) == 5
    assert all(c.credit == "www.foto-webcam.eu" and c.fit == "scaled" and c.supports_offset for c in theirs)


def test_yosemite_cams_are_never_cropped():
    theirs = [c for c in builtin().values() if c.id.startswith("yosemite-")]
    assert len(theirs) == 5 and all(c.fit == "scaled" for c in theirs)


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
