"""Core conversion pipeline (docs/design/02-conversion-pipeline.md).

Stage order (do not reorder without reading 02-conversion-pipeline.md §4 first,
each step's position was chosen deliberately):
  1. remove_background     - subject isolation (rembg)                    -> background_removal.py
  2. crop_and_center        - bounding-box crop to a square, with margin   -> crop.py
  2.5 suppress_mouth        - paint over a mouth-like mark with skin color -> mouth.py
  3. downsample             - shrink to the pixel grid                    -> downsample.py
  4. quantize_colors        - banded per-region MAXCOVERAGE + merge       -> quantize.py
  4.5 fix_color_conflation  - safety-net cleanup for residual color reuse -> quantize.py
  5. add_outline            - 1px dark outline along the alpha boundary   -> render.py
  6. upscale                - NEAREST upscale to a power-of-two export    -> render.py

Split into per-stage modules (2026-07-28) so each stage's bug history and
logic can be found and fixed independently. This file stays a thin
orchestrator (`convert()`) plus re-exports so existing callers
(`app/main.py`, `scripts/*.py`) keep working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from app.background_removal import remove_background
from app.crop import MAX_ASPECT_RATIO, CropInfo, UnsupportedPoseError, crop_and_center
from app.downsample import downsample
from app.mouth import suppress_mouth
from app.quantize import quantize_colors, fix_color_conflation, fix_stray_band_pixels
from app.render import OUTLINE_COLOR, add_outline, upscale

__all__ = [
    "OUTLINE_COLOR",
    "MAX_ASPECT_RATIO",
    "UnsupportedPoseError",
    "CropInfo",
    "remove_background",
    "crop_and_center",
    "suppress_mouth",
    "downsample",
    "quantize_colors",
    "fix_color_conflation",
    "fix_stray_band_pixels",
    "add_outline",
    "upscale",
    "ConversionResult",
    "convert",
]


@dataclass
class ConversionResult:
    final: Image.Image  # after stage 6, ready to export
    pre: Image.Image  # after stage 2, before stage 3 (for eye-landmark detection later)
    crop_info: CropInfo
    quantized_reference: Image.Image  # stage-4 output, RGBA, small grid - reusable as a palette source


def convert(
    image: Image.Image,
    grid_size: int = 32,
    colors: int = 8,
    output_size: int = 64,
    outline: bool = True,
    palette_source: Image.Image | None = None,
    model_name: str = "u2netp",
) -> ConversionResult:
    """Runs the full pipeline (docs/design/02-conversion-pipeline.md §1) on one image."""
    removed = remove_background(image, model_name=model_name)
    pre, crop_box = crop_and_center(removed)
    pre = suppress_mouth(pre)
    small = downsample(pre, grid_size=grid_size)
    quantized = quantize_colors(small, colors=colors, palette_source=palette_source)
    if palette_source is None:
        # Only the view establishing the palette needs conflation-fixing.
        # Views snapping to an already-decided palette (palette_source given,
        # docs/design/06-multi-angle-input.md §5) would otherwise run this a
        # second time on an already-quantized image, re-splitting a color the
        # source view already separated (at a different split point) and
        # pulling in a brand new averaged color not in that shared palette at
        # all - found via a real user report of skin tone drifting between
        # views (colors=8 was producing 13 colors on front but 20 on
        # diagonal). Skipping it here keeps every non-primary view's palette
        # an exact subset of the primary view's.
        quantized = fix_color_conflation(quantized, small)
    else:
        # Other views must stay within the shared front-derived palette
        # (docs/design/06-multi-angle-input.md §5), so they can't run
        # fix_color_conflation() itself (see the comment above). But they can
        # still suffer their own, narrower version of the same problem - a
        # small facial-highlight color landing, by nearest-RGB-distance alone,
        # on an isolated pixel far away on the body (real user report:
        # diagonal views showing stray red/pink pixels on the torso that
        # aren't in the front view). fix_stray_band_pixels() fixes only that
        # narrow case without ever introducing a color outside the shared
        # palette (see its docstring in quantize.py for why
        # fix_color_conflation() itself isn't reused here).
        quantized = fix_stray_band_pixels(quantized, small)
    outlined = add_outline(quantized) if outline else quantized
    final = upscale(outlined, output_size=output_size)

    scale = pre.width / grid_size
    return ConversionResult(
        final=final,
        pre=pre,
        crop_info=CropInfo(crop_box=crop_box, scale=scale),
        quantized_reference=quantized,
    )
