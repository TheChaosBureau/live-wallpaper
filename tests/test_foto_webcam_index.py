# SPDX-License-Identifier: Apache-2.0
from live_wallpaper.cams import parse_cams
from live_wallpaper.foto_webcam_index import cams_from_index


def entry(**kw):
    base = {"id": "zugspitze", "title": "Wetterwarte Zugspitze - Blick nach Osten", "offline": False,
            "hidden": False, "partner": False, "captureInterval": 1800,
            "imgurl": "https://www.foto-webcam.eu/webcam/zugspitze/current/400.jpg"}
    base.update(kw)
    return base


def test_an_ordinary_cam_becomes_a_credited_uncropped_archive_cam():
    (cam,) = cams_from_index({"cams": [entry()]})
    assert cam == {"id": "alps-zugspitze", "name": "Wetterwarte Zugspitze - Blick nach Osten",
                   "kind": "foto-webcam", "url": "https://www.foto-webcam.eu", "cam": "zugspitze",
                   "interval_minutes": 10, "fit": "scaled", "credit": "www.foto-webcam.eu"}
    parse_cams([cam])        # and the app accepts it


def test_hourly_cams_get_an_hourly_interval():
    (cam,) = cams_from_index({"cams": [entry(captureInterval=3600)]})
    assert cam["interval_minutes"] == 60


def test_interval_given_as_text_is_understood():
    (cam,) = cams_from_index({"cams": [entry(captureInterval="600")]})
    assert cam["interval_minutes"] == 10


def test_cams_that_are_not_theirs_or_not_running_are_left_out():
    skipped = [
        entry(id="a", offline=True),
        entry(id="b", hidden=True),
        entry(id="c", partner=True),
        entry(id="d", imgurl="https://terra-hd.com/webcam/d/current/400.jpg"),
        entry(id="e", captureInterval=0),
        entry(id="f", captureInterval=31536000),
        entry(id="Bad Id"),
        entry(id="g", title="  "),
    ]
    assert cams_from_index({"cams": skipped}) == []


def test_sorted_by_name_and_names_are_single_lines():
    cams = cams_from_index({"cams": [entry(id="b", title="Zell am See\n- Blick"), entry(id="a", title="Achensee")]})
    assert [c["name"] for c in cams] == ["Achensee", "Zell am See - Blick"]
