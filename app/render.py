"""Stages 5-6: outline and final upscale (docs/design/02-conversion-pipeline.md §2⑤⑥).

Split out of pipeline.py (2026-07-28). These two stages are simple and stable
(no bug history) - kept together in one small file rather than split further.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

OUTLINE_COLOR = (0x1A, 0x1C, 0x2C, 0xFF)  # docs/design/01-visual-concept.md outline color


def add_outline(image: Image.Image, outline_color: tuple[int, int, int, int] = OUTLINE_COLOR) -> Image.Image:
    """Paint a 1px outline along the alpha boundary."""
    arr = np.array(image)  # H, W, 4
    alpha = arr[:, :, 3]
    opaque = alpha > 0

    # a pixel is "boundary" if it's opaque and has at least one transparent
    # 4-neighbor (simple dilation-based edge detection, no extra deps needed)
    padded = np.pad(opaque, 1, mode="constant", constant_values=False)
    neighbor_transparent = (
        ~padded[:-2, 1:-1] | ~padded[2:, 1:-1] | ~padded[1:-1, :-2] | ~padded[1:-1, 2:]
    )
    boundary = opaque & neighbor_transparent

    out = arr.copy()
    out[boundary] = outline_color
    return Image.fromarray(out, mode="RGBA")


def upscale(image: Image.Image, output_size: int = 64) -> Image.Image:
    """NEAREST upscale to the final export size (keeps hard pixel edges)."""
    return image.resize((output_size, output_size), resample=Image.NEAREST)
