# SPDX-License-Identifier: Apache-2.0
"""Stamping a small credit line on a frame, for cams whose owners ask for one."""

from __future__ import annotations

import io

from .fetch import FetchError


def stamp(data: bytes, text: str) -> bytes:
    """Return the JPEG with `text` drawn small in the bottom-right corner."""
    from PIL import Image, ImageDraw, ImageFont  # imported here: only credited cams need it

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        raise FetchError(f"the picture could not be read to add its credit line: {exc}") from exc
    image = image.convert("RGB")
    width, height = image.size
    size = max(10, round(height * 0.016))
    margin = max(6, round(height * 0.012))
    font = ImageFont.load_default(size=size)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    x = width - margin - (right - left) - left
    y = height - margin - (bottom - top) - top
    # light text with a dark edge, so it reads on snow and on night sky alike
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 215),
              stroke_width=max(1, size // 12), stroke_fill=(0, 0, 0, 150))
    out = io.BytesIO()
    Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB").save(
        out, "JPEG", quality=93, subsampling=0)
    return out.getvalue()
