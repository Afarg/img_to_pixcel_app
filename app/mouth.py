"""Stage 2.5: mouth suppression (docs/design/02-conversion-pipeline.md §2②.5).

Runs right after crop_and_center(), before downsample/quantize, so every
downstream artifact (all views' final.png, and the pre.png ani_convert_app
reads for blink/walk generation) is already mouth-free - there's nothing
elsewhere in the pipeline that needs separate mouth-awareness.
"""

from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage


def suppress_mouth(
    pre_image: Image.Image,
    skin_reference_band: tuple[float, float] = (0.40, 0.44),
    mouth_search_band: tuple[float, float] = (0.44, 0.56),
    width_fraction: float = 0.30,
    darkness_threshold: int = 80,
    min_area: int = 4,
    max_area: int = 800,
) -> Image.Image:
    """Paints over a mouth-like mark with the surrounding skin color, so the
    character never displays a mouth (user request: a visible mouth implies
    an expression/emotion that can bias how the character reads).

    Unlike eyes (found in `ani_convert_app/app/blink.py` via high saturation -
    eyes are usually a vivid color), a simple line-mouth is typically a dark,
    desaturated mark against lighter skin (verified empirically against a
    real character: the mouth's RGB channels were near-equal - i.e. grey,
    not colored - and much darker than the surrounding skin). So the signal
    used here is darkness relative to the local skin tone, not saturation.

    Two separate bands (fractions of the character's own bbox height) are
    used rather than one:

    - `skin_reference_band`: a narrow strip just below the eye line, used
      ONLY to measure what this character's actual skin color is.
    - `mouth_search_band`: a wider strip below that, where the mouth is
      actually looked for.

    A single combined band was tried first and failed empirically: on a real
    character, a band wide enough to reliably contain the mouth also reached
    down into the jacket collar, and the collar's dark pixels dominated the
    band's own "what counts as skin" statistic (median luminance dropped to
    roughly a third of the true skin tone), so the real mouth mark no longer
    registered as "darker than skin" and nothing was suppressed. Establishing
    the skin reference from a narrower, collar-free strip above the search
    band avoids that contamination regardless of how much non-skin content
    the search band itself ends up containing (this is the same lesson as
    `ani_convert_app/app/walk.py`'s `shift_fraction` fix - a single
    bbox-fraction band is fragile once clothing extends into it).

    Both bands are further restricted to a horizontal window centered on the
    character's own midline (`width_fraction` of bbox width) - a real mouth
    is small and roughly centered, unlike hair/ears/clothing at the sides.

    Within `mouth_search_band`, pixels darker than the `skin_reference_band`
    median luminance by more than `darkness_threshold` are candidates;
    connected candidates are grouped and the whole thing is skipped if
    nothing plausibly mouth-sized (`min_area`-`max_area`) is found - fail
    soft rather than guess, same philosophy as blink.py's eye detection. The
    matched region is filled with the `skin_reference_band` color.

    KNOWN ISSUE (docs/project-status.md §10-11, 2026-08-15): on a 3-head-tall
    character, these height-based bands land on the coat's front seam (a
    dark vertical line) instead of the face, erasing part of it. A width-
    based band fix analogous to blink.py's `detect_eyes()` refinement 5 was
    attempted and reverted - it stopped the coat-seam false positive but
    introduced new ones on the collar/neckline for two other test
    characters instead.

    Follow-up investigation found the problem goes deeper than band
    placement: `skin_reference_band` itself was measured to sample the
    WRONG color on some of those characters, under both the original and
    the attempted width-based bands - purple coat fabric for one character,
    black hair for another, neither anywhere close to actual skin tone. Once
    `skin_color` itself is wrong, no downstream check (e.g. "is this
    candidate's surrounding ring close to skin_color") can work, since it's
    being compared against a bad reference. Unlike `detect_eyes()`, which
    had saturation and left-right pairing as independent, position-
    tolerant signals to fall back on, there is currently no equally robust
    way here to locate "the actual skin" without already knowing where the
    face is - this needs a real design pass (e.g. robustly locating the
    face region first, then sampling skin from within it), not a small
    parameter tweak. Deliberately left unfixed this session rather than
    ship another guess.
    """
    arr = np.array(pre_image.convert("RGBA"))
    alpha = arr[:, :, 3]
    opaque = alpha > 0
    ys, xs = np.where(opaque)
    if len(ys) == 0:
        return pre_image

    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    center_x = (x0 + x1) / 2
    half_w = (x1 - x0) * width_fraction / 2
    win_x0 = max(x0, int(center_x - half_w))
    win_x1 = min(x1, int(center_x + half_w))

    def band_mask_for(band: tuple[float, float]) -> np.ndarray:
        by0 = y0 + int((y1 - y0) * band[0])
        by1 = y0 + int((y1 - y0) * band[1])
        mask = np.zeros_like(opaque)
        mask[by0 : by1 + 1, win_x0 : win_x1 + 1] = opaque[by0 : by1 + 1, win_x0 : win_x1 + 1]
        return mask

    rgb = arr[:, :, :3].astype(np.int32)
    luminance = rgb.sum(axis=2)

    ref_mask = band_mask_for(skin_reference_band)
    if not ref_mask.any():
        return pre_image
    skin_color = np.median(rgb[ref_mask], axis=0)
    skin_luminance = float(np.median(luminance[ref_mask]))

    search_mask = band_mask_for(mouth_search_band)
    if not search_mask.any():
        return pre_image

    dark_mask = search_mask & (luminance < skin_luminance - darkness_threshold)
    if not dark_mask.any():
        return pre_image  # no plausible mouth mark - leave the character as is

    labeled, num_labels = ndimage.label(dark_mask)
    best_label, best_area = None, 0
    for i in range(1, num_labels + 1):
        area = int((labeled == i).sum())
        if min_area <= area <= max_area and area > best_area:
            best_label, best_area = i, area
    if best_label is None:
        return pre_image

    # Dilate by 1px: the anti-aliased soft edge around the mouth mark is
    # lighter than its core and often doesn't clear `darkness_threshold` on
    # its own, leaving a faint outline behind if only the core is repainted
    # (found empirically). A small dilation folds that fringe in too.
    mouth_mask = ndimage.binary_dilation(labeled == best_label, iterations=1) & search_mask
    out = arr.copy()
    out[mouth_mask, :3] = np.clip(skin_color, 0, 255).round().astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")
