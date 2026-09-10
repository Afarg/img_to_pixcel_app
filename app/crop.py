"""Stage 2: auto-crop, center, and pose validation (docs/design/02-conversion-pipeline.md §2②).

Split out of pipeline.py (2026-07-28) for the same reason as the other stage
modules: each stage gets its own small, independently-testable file.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

# Max allowed (bbox width / bbox height) of the detected silhouette. A normal
# standing character (arms at sides) is portrait-shaped (narrow); a T-pose /
# arms-spread reference image pushes this close to or above 1.0. Verified
# empirically: a synthetic standing figure measured ~0.42; a real T-pose chibi
# illustration measured far above this threshold (docs/design/04 update).
# Deliberately a hard error rather than a silent best-effort squash - a T-pose
# input degrades badly (torso/legs get compressed into a thin vertical strip)
# and it's better to ask the user for a different photo than to ship a bad
# result (docs/design/04-constraints-and-limitations.md §4 "失敗時の挙動方針"
# still applies to background-removal failures; this is a distinct, new
# validation the user asked for after seeing the T-pose failure mode firsthand).
MAX_ASPECT_RATIO = 0.75


class UnsupportedPoseError(ValueError):
    """Raised when the detected silhouette is too wide relative to its height
    (docs/design/04-constraints-and-limitations.md) - e.g. a T-pose / arms-spread
    reference image instead of a normal standing character."""


@dataclass
class CropInfo:
    """Coordinates needed to map a point on the pre-downsample image to the
    final small grid (docs/design/06-multi-angle-input.md §5, manifest `cropBox`/`scale`).
    """

    crop_box: tuple[int, int, int, int]  # (left, top, right, bottom) on the ORIGINAL input image
    scale: float  # pre-image px per final-grid px (pre_size / grid_size)


def crop_and_center(
    image: Image.Image, margin_ratio: float = 0.10, max_aspect_ratio: float = MAX_ASPECT_RATIO
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Crop to the alpha bounding box (with margin) and pad to a square.

    Returns (cropped_square_image, crop_box_on_original_image).

    Raises UnsupportedPoseError if the silhouette is wider than
    `max_aspect_ratio` times its height (T-pose / arms-spread input).
    """
    alpha = image.split()[-1]
    bbox = alpha.getbbox()
    if bbox is None:
        # Nothing detected as foreground (fully transparent) - fall back to the
        # whole image rather than crash (docs/design/04-constraints-and-limitations.md §4).
        bbox = (0, 0, image.width, image.height)

    left, top, right, bottom = bbox
    w, h = right - left, bottom - top

    aspect_ratio = w / h if h else float("inf")
    if aspect_ratio > max_aspect_ratio:
        raise UnsupportedPoseError(
            f"検出したキャラクターの幅/高さ比が {aspect_ratio:.2f} で、上限 {max_aspect_ratio} を超えています。"
            "腕を広げたポーズ(Tポーズ等)は非対応です。腕を下ろした正面立ちの画像を使用してください。"
        )

    margin_x = int(w * margin_ratio)
    margin_y = int(h * margin_ratio)
    left = max(0, left - margin_x)
    top = max(0, top - margin_y)
    right = min(image.width, right + margin_x)
    bottom = min(image.height, bottom + margin_y)

    cropped = image.crop((left, top, right, bottom))

    # pad to square (transparent padding) so the character isn't stretched later
    side = max(cropped.width, cropped.height)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    paste_x = (side - cropped.width) // 2
    paste_y = (side - cropped.height) // 2
    square.paste(cropped, (paste_x, paste_y))

    return square, (left, top, right, bottom)
