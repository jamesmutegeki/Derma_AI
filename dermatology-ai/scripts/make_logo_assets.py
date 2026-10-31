#!/usr/bin/env python3
"""Generate the logo assets from the supplied artwork.

The project needs three files and no more:

* ``assets/logo.png``        -- full lockup (emblem + "DERMATOLOGY SYSTEM")
* ``assets/logo-mark.png``   -- the emblem alone, square, transparent
* ``assets/favicon.png``     -- small square mark for the browser tab

Everything derives from ``assets/logo-source.jpg`` so the build is reproducible:
replace the source, re-run this script, commit the outputs.

Why the artwork is *classified* rather than simply keyed out: the source is a
JPEG of a two-colour mark on a near-white page, so a naive "white becomes
transparent" pass turns compression noise into coloured speckle. Instead each
pixel is snapped to the nearest brand colour (or to background), the page is
dropped, and the result is downscaled with a high-quality filter -- which also
gives clean anti-aliased edges at the small sizes the interface uses.

Usage:
    python scripts/make_logo_assets.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

APP_DIR = Path(__file__).resolve().parents[1]
ASSETS = APP_DIR / "assets"
SOURCE = ASSETS / "logo-source.jpg"

# Brand colours, refined at run time from the artwork itself.
FALLBACK_INK = [(20, 54, 95), (226, 96, 92)]  # navy, coral
SNAP_DISTANCE = 110      # beyond this a pixel is background, not artwork
BACKGROUND = (255, 255, 255)


def _bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    if not len(rows) or not len(cols):
        raise SystemExit("source image appears to be blank")
    return int(cols.min()), int(rows.min()), int(cols.max()), int(rows.max())


def _brand_colours(rgb: np.ndarray) -> list[tuple[int, int, int]]:
    """Recover the two ink colours from the most saturated pixels."""
    spread = rgb.max(axis=2) - rgb.min(axis=2)
    pixels = rgb[spread > 45]
    if len(pixels) < 100:
        return list(FALLBACK_INK)

    quantised = (pixels // 24) * 24
    colours, counts = np.unique(quantised.reshape(-1, 3), axis=0, return_counts=True)
    order = np.argsort(counts)[::-1]
    chosen: list[tuple[int, int, int]] = []
    for index in order:
        candidate = tuple(int(v) for v in colours[index])
        if all(sum((a - b) ** 2 for a, b in zip(candidate, other)) > 90 ** 2
               for other in chosen):
            chosen.append(candidate)
        if len(chosen) == 2:
            break

    if len(chosen) < 2:
        return list(FALLBACK_INK)
    # Refine each cluster to the mean of its own members.
    refined = []
    for centre in chosen:
        delta = ((pixels - np.array(centre)) ** 2).sum(axis=1)
        members = pixels[delta < 60 ** 2]
        refined.append(tuple(int(v) for v in members.mean(axis=0)) if len(members)
                       else centre)
    return refined


def _classify(rgb: np.ndarray, inks: list[tuple[int, int, int]]) -> Image.Image:
    """Snap every pixel to an ink colour or to transparent background."""
    palette = np.array(inks + [BACKGROUND], dtype=np.int32)
    distances = ((rgb[:, :, None, :].astype(np.int32) - palette[None, None, :, :]) ** 2).sum(axis=3)
    nearest = distances.argmin(axis=2)
    best = distances.min(axis=2)
    background_index = len(inks)

    rgba = np.zeros((*rgb.shape[:2], 4), dtype=np.uint8)
    for index, colour in enumerate(palette):
        selected = (nearest == index) & (best <= SNAP_DISTANCE ** 2)
        if index == background_index:
            continue
        rgba[selected, 0:3] = colour
        rgba[selected, 3] = 255
    return Image.fromarray(rgba, mode="RGBA")


def _pad_square(image: Image.Image, size: int) -> Image.Image:
    width, height = image.size
    side = max(width, height)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - width) // 2, (side - height) // 2), image)
    return canvas.resize((size, size), Image.LANCZOS)


def main() -> int:
    if not SOURCE.is_file():
        raise SystemExit(f"missing source artwork: {SOURCE}")
    ASSETS.mkdir(parents=True, exist_ok=True)

    source = Image.open(SOURCE).convert("RGB").filter(ImageFilter.MedianFilter(3))
    rgb = np.asarray(source).astype(np.int32)
    inks = _brand_colours(rgb)
    clean = _classify(rgb, inks)
    print("ink colours:", inks)

    left, top, right, bottom = _bbox(np.asarray(clean)[:, :, 3] > 0)

    # The wordmark starts after a clear horizontal gap under the emblem.
    ink_rows = (np.asarray(clean)[:, :, 3] > 0).sum(axis=1)
    emblem_bottom = bottom + 1
    gap_start = None
    for y in range(top, bottom + 1):
        if ink_rows[y] < 3:
            if gap_start is None:
                gap_start = y
        elif gap_start is not None:
            if y - gap_start > 8:
                emblem_bottom = gap_start
                break
            gap_start = None

    # A little breathing room: cropping exactly on the ink clips the
    # anti-aliased edge when the asset is resampled.
    pad = max(4, round((right - left) * 0.015))
    box = (max(0, left - pad), max(0, top - pad),
           min(clean.width, right + pad), min(clean.height, bottom + pad))
    mark = clean.crop((box[0], box[1], box[2], min(clean.height, emblem_bottom + pad)))
    lockup = clean.crop(box)

    _pad_square(mark, 512).save(ASSETS / "logo-mark.png", optimize=True)

    lockup_width = 640
    lockup_height = round(lockup.height * lockup_width / lockup.width)
    lockup.resize((lockup_width, lockup_height), Image.LANCZOS).save(
        ASSETS / "logo.png", optimize=True)

    _pad_square(mark, 128).save(ASSETS / "favicon.png", optimize=True)

    for name in ("logo.png", "logo-mark.png", "favicon.png"):
        path = ASSETS / name
        with Image.open(path) as produced:
            print(f"{name}: {produced.size} {produced.mode} {path.stat().st_size // 1024} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
