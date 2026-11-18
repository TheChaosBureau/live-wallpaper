# SPDX-License-Identifier: Apache-2.0
import io

import pytest
from PIL import Image, ImageChops

from live_wallpaper.fetch import FetchError
from live_wallpaper.stamp import stamp


def jpeg(width=1920, height=1080, colour=(40, 90, 140)):
    out = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(out, "JPEG", quality=95)
    return out.getvalue()


def changed_box(before, after):
    a = Image.open(io.BytesIO(before)).convert("RGB")
    b = Image.open(io.BytesIO(after)).convert("RGB")
    diff = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 40 else 0)
    return diff.getbbox(), b.size


def test_result_is_a_jpeg_of_the_same_size():
    src = jpeg()
    out = stamp(src, "www.example.org")
    assert out[:3] == b"\xff\xd8\xff"
    assert Image.open(io.BytesIO(out)).size == (1920, 1080)


def test_text_is_small_and_in_the_bottom_right_corner():
    src = jpeg()
    box, (w, h) = changed_box(src, stamp(src, "www.example.org"))
    assert box is not None, "nothing was drawn"
    left, top, right, bottom = box
    assert left > w * 0.6 and top > h * 0.9          # confined to the corner
    assert right <= w and bottom <= h
    assert (bottom - top) < h * 0.05                 # small


def test_text_scales_with_the_image():
    small, _ = changed_box(jpeg(960, 540), stamp(jpeg(960, 540), "www.example.org"))
    large, _ = changed_box(jpeg(3840, 2160), stamp(jpeg(3840, 2160), "www.example.org"))
    assert (large[3] - large[1]) > 2.5 * (small[3] - small[1])


def test_readable_on_a_white_image_too():
    src = jpeg(colour=(255, 255, 255))
    box, _ = changed_box(src, stamp(src, "www.example.org"))
    assert box is not None


def test_not_an_image_is_a_fetch_error():
    with pytest.raises(FetchError):
        stamp(b"\xff\xd8\xff this is not really a jpeg", "www.example.org")
