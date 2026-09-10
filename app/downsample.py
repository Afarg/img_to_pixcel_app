"""Stage 3: shrink to the pixel grid (docs/design/02-conversion-pipeline.md §2③).

Split out of pipeline.py (2026-07-28). This stage has been the site of two
real bug fixes (thin limbs vanishing, fine linework turning fabric gray) - see
`_representative_color()`'s docstring for the full history. Keeping it in its
own file makes it easier to find and reason about the next time.
"""

from __future__ import annotations

import numpy as np
from PIL import Image


def _representative_color(
    region_rgb: np.ndarray,
    region_alpha: np.ndarray,
    dark_max_threshold: float = 55.0,
    min_dark_fraction_to_keep: float = 0.35,
) -> np.ndarray:
    """Returns a representative color for one destination cell: an
    alpha-weighted mean, but near-black "outline-like" pixels are excluded
    from that mean when they're only a MINORITY of the cell's coverage.

    Two other approaches were tried first and both failed one of the two
    real test cases (see docs/design/02-conversion-pipeline.md §4 for the
    full write-up):

    - A plain alpha-weighted mean (no exclusion) correctly preserved small
      colorful features like eyes (a minority-colored blend is still enough
      for stage 4's quantizer to notice and give its own palette slot), but
      a character with lots of fine black linework on white fabric (buttons,
      seams, a detailed mask pattern) came out visibly gray/muddy - a cell
      that's mostly white fabric crossed by a thin black seam line
      unavoidably averages toward gray.
    - A pure MODE (most-common-color-bucket) fixed the fabric/linework case
      cleanly, but then a *different* character's eyes disappeared entirely:
      an eye occupying a minority of a cell lost every vote to the
      surrounding skin/hair, unlike a mean which at least leaves a trace.

    The fix: only exclude a cell's dark pixels from the color average if
    they're a MINORITY of that cell's weight - i.e., treat thin near-black
    outline strokes crossing through an otherwise-light cell as expected
    line-art detail that's lost at this resolution (this is also
    stylistically authentic - real retro pixel art drops sub-pixel linework
    too), while a cell that's genuinely mostly dark (dark fabric, hair
    shadow, ...) still gets its dark color, since there "dark" isn't stray
    outline noise, it's the actual content. Eyes are neither near-black nor
    typically the darkness-majority of their cell, so this rule doesn't
    touch them - they still get a plain weighted-mean blend as before.
    """
    opaque = region_alpha > 0
    if not opaque.any():
        return np.zeros(3)

    weights = region_alpha
    brightness = region_rgb.max(axis=-1)
    dark = opaque & (brightness < dark_max_threshold)
    non_dark = opaque & ~dark

    dark_weight = weights[dark].sum()
    non_dark_weight = weights[non_dark].sum()
    total_weight = dark_weight + non_dark_weight

    use_mask = non_dark if (non_dark_weight > 0 and dark_weight < total_weight * min_dark_fraction_to_keep) else opaque

    w = weights[use_mask]
    return (region_rgb[use_mask] * w[:, None]).sum(axis=0) / w.sum()


def downsample(image: Image.Image, grid_size: int = 32, alpha_threshold: int = 60) -> Image.Image:
    """Shrink to the pixel grid.

    Three things were fixed here after empirical testing on real characters
    (see docs/design/02-conversion-pipeline.md §4's update for the full history):

    1. Alpha uses MAX-pooling, not averaging. A plain BOX/average resize
       treats a thin limb the same as any other partial-coverage edge pixel:
       if a limb covers say 20% of a destination cell, the averaged alpha
       ends up around 0.2*255=51, which is easy to threshold away entirely -
       exactly what was happening to arms/legs. Max-pooling means "if ANY
       part of this cell touched the character, keep it", which preserves
       thin protruding structures instead of averaging them into nothing.
    2. Color was alpha-weighted (not a plain average) to stop transparent
       background pixels' RGB from bleeding into edge colors.
    3. Color excludes minority near-black "outline-like" pixels from that
       weighted average (see `_representative_color()` for the full
       reasoning and the two alternatives - a plain mean, then a pure mode -
       that were each tried and rejected first for failing one of two real
       test cases).
    """
    arr = np.asarray(image.convert("RGBA"), dtype=np.float64)
    h, w = arr.shape[:2]
    out = np.zeros((grid_size, grid_size, 4), dtype=np.uint8)

    for gy in range(grid_size):
        y0 = h * gy // grid_size
        y1 = max(y0 + 1, h * (gy + 1) // grid_size)
        for gx in range(grid_size):
            x0 = w * gx // grid_size
            x1 = max(x0 + 1, w * (gx + 1) // grid_size)
            region = arr[y0:y1, x0:x1]
            region_alpha = region[:, :, 3]
            max_alpha = region_alpha.max()

            rgb = _representative_color(region[:, :, :3], region_alpha) if max_alpha > 0 else np.zeros(3)

            out[gy, gx, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
            out[gy, gx, 3] = 255 if max_alpha >= alpha_threshold else 0

    return Image.fromarray(out, mode="RGBA")
