"""Stage 4 (+4.5): palette reduction (docs/design/02-conversion-pipeline.md §2④).

Split out of pipeline.py (2026-07-28). This is the stage with the longest
trial-and-error history in the whole pipeline (four rejected approaches before
the current one, see `quantize_colors()`'s docstring) - a dedicated file makes
that history and the current logic easier to find together.
"""

from __future__ import annotations

import numpy as np
from PIL import Image


def _merge_close_candidates(candidates: list[tuple[np.ndarray, float]], merge_distance: float) -> list[tuple[np.ndarray, float]]:
    """candidates: (rgb, weight) pairs. Weighted-average any pair closer than
    merge_distance together, repeatedly, until no more merges apply."""
    merged: list[list] = [[rgb, weight] for rgb, weight in candidates]
    changed = True
    while changed:
        changed = False
        for i in range(len(merged)):
            for j in range(i + 1, len(merged)):
                if merged[i] is None or merged[j] is None:
                    continue
                if np.linalg.norm(merged[i][0] - merged[j][0]) < merge_distance:
                    total = merged[i][1] + merged[j][1]
                    merged[i][0] = (merged[i][0] * merged[i][1] + merged[j][0] * merged[j][1]) / total
                    merged[i][1] = total
                    merged[j] = None
                    changed = True
        merged = [m for m in merged if m is not None]
    return [(m[0], m[1]) for m in merged]


def _reduce_to_k(entries: list[tuple[np.ndarray, float]], k: int) -> list[tuple[np.ndarray, float]]:
    """Repeatedly merge the CLOSEST remaining pair (regardless of weight)
    until at most k entries remain.

    Originally this picked the least-weighted entry and folded it into its
    nearest neighbor - simple, but empirically it re-introduced the very
    problem per-band MAXCOVERAGE was meant to solve: a rare eye-red candidate
    from one band has a small weight compared to a hair/jacket candidate from
    another band, so it kept getting selected as "least weighted" and merged
    away before the color budget was exhausted, even though it was never
    close to any other remaining candidate. Merging the closest pair instead
    means a genuinely distinct color (far from everything else in RGB space)
    is only forced to merge once no more-similar pair exists anywhere - much
    closer to MAXCOVERAGE's own "keep distinct colors distinct" philosophy.
    """
    entries = [[rgb, weight] for rgb, weight in entries]
    while len(entries) > k:
        best_i = best_j = None
        best_dist = float("inf")
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                d = np.linalg.norm(entries[i][0] - entries[j][0])
                if d < best_dist:
                    best_dist = d
                    best_i, best_j = i, j
        rgb_i, w_i = entries[best_i]
        rgb_j, w_j = entries[best_j]
        total = w_i + w_j
        entries[best_i] = [(rgb_i * w_i + rgb_j * w_j) / total, total]
        entries.pop(best_j)
    return [(rgb, weight) for rgb, weight in entries]


def quantize_colors(
    image: Image.Image,
    colors: int = 6,
    palette_source: Image.Image | None = None,
    bands: int = 5,
) -> Image.Image:
    """Reduce to a small palette.

    History of approaches tried, in order (see docs/design/02-conversion-pipeline.md
    §4 for the full write-up):

    1. Quantizing RGBA directly (FASTOCTREE) burned the color budget on the
       large dark hair/jacket area and dropped the small face/skin region
       entirely.
    2. Splitting alpha out and using Pillow's MAXCOVERAGE on plain RGB fixed
       that, but MAXCOVERAGE (like any global histogram-based quantizer) has
       no notion of WHERE a color is - a dark eye-shadow tone and an unrelated
       dark shoe tone landed in the same palette entry purely because they
       were RGB-close, so the eye's color visibly "appeared" on the shoes
       despite being unrelated, far-apart features (user report, reproduced at
       grid=64, colors=10).
    3. A spatially-augmented k-means (clustering on R,G,B,x,y) fixed the
       shoe/eye case but reintroduced problem #1 - plain k-means is still
       population-greedy and dropped the eyes.
    4. A post-process that detected and split conflated colors after the fact
       worked for a clean two-region case, but this specific character's dark
       tone is used continuously across many regions (hair shadow, neck,
       jacket seams, shoes) with no single clean gap to split on, so it didn't
       help here.

    This version (adopted per the user's suggestion): **partition first, then
    quantize per-partition, then merge.** The image is split into `bands`
    horizontal bands (a crude, deterministic stand-in for "body parts" - head/
    neck/torso/legs/feet - without needing real pose detection). Each band's
    OWN colors are found independently via k-means restricted to just that
    band's pixels, so a small feature (like eyes) only has to stand out
    relative to its own band's population (mostly hair/face), not the whole
    character. Bands' candidate colors are then merged: near-duplicates
    (e.g. the same jacket blue appearing in two adjacent bands) are combined,
    and if still over the `colors` budget, the least-used candidates are
    folded into their nearest remaining neighbor. Because a shoe's brown and
    an eye's red only ever "meet" at this final merge step - and only get
    merged if they're still close enough in RGB after each already had a
    chance to claim its own slot within its own band - they no longer compete
    for the same slot the way a single global histogram would force them to.

    If `palette_source` is given (an already-quantized RGBA image), reuse its
    palette instead of deriving a new one - this is how multi-angle consistency
    is kept (docs/design/06-multi-angle-input.md §4): the front view's palette
    is authoritative and other views snap to it. Banding doesn't apply to this
    path - it's just applying an already-decided palette.
    """
    alpha_img = image.split()[-1]

    if palette_source is not None:
        # Pillow's quantize(palette=...) requires a "P"-mode (paletted) image,
        # not a plain RGB one - passing quantized_reference straight through
        # (RGB after dropping alpha) raises "bad mode for palette image".
        # Re-quantizing it to its own distinct colors turns it into a P-mode
        # image losslessly (it already has at most `colors` distinct colors),
        # giving a real palette for the other view to snap to.
        #
        # `.convert("RGB")` drops alpha, so the transparent background
        # (RGBA (0,0,0,0)) becomes an opaque-looking (0,0,0) black - a color
        # that was never actually visible in palette_source. Left in, it
        # steals a palette slot from a real color (found via a real user
        # report + reproduction at grid_size=128, colors=10: front had 16
        # real colors but distinct_count came out to 17, and diagonal views'
        # real near-black outline pixels started snapping to this phantom
        # background slot instead of front's actual near-black outline
        # color - producing a genuinely new, wrong color in the opaque
        # region, on top of inflating the view's color count past front's).
        # Blanking the transparent area to an existing opaque color before
        # deriving distinct_count/the palette keeps both accurate.
        source_rgb_arr = np.array(palette_source.convert("RGB"))
        source_opaque = np.array(palette_source.split()[-1]) > 0
        if source_opaque.any():
            distinct_count = len(np.unique(source_rgb_arr[source_opaque], axis=0))
            source_rgb_arr = source_rgb_arr.copy()
            source_rgb_arr[~source_opaque] = source_rgb_arr[source_opaque][0]
        else:
            distinct_count = 1
        source_rgb = Image.fromarray(source_rgb_arr, mode="RGB")
        palette_img = source_rgb.quantize(colors=max(1, min(256, distinct_count)), dither=Image.Dither.NONE)

        rgb_img = image.convert("RGB")
        quantized_rgb = rgb_img.quantize(palette=palette_img, dither=Image.Dither.NONE)
        result = quantized_rgb.convert("RGBA")
        result.putalpha(alpha_img)
        return result

    alpha_arr = np.array(alpha_img)
    h, w = alpha_arr.shape
    rgb_arr = np.array(image.convert("RGB"), dtype=np.float64)
    opaque = alpha_arr > 0

    rows_used = np.where(opaque.any(axis=1))[0]
    out = np.zeros((h, w, 4), dtype=np.uint8)
    if len(rows_used) == 0:
        return Image.fromarray(out, mode="RGBA")

    y0, y1 = int(rows_used.min()), int(rows_used.max())
    band_height = max(1.0, (y1 - y0 + 1) / bands)
    colors_per_band = max(2, -(-colors * 3 // 4))  # ~75% of budget per band, intentionally allows overlap pre-merge

    candidates: list[tuple[np.ndarray, float]] = []
    for b in range(bands):
        band_y0 = int(y0 + b * band_height)
        band_y1 = int(y0 + (b + 1) * band_height) if b < bands - 1 else y1 + 1
        band_opaque = opaque[band_y0:band_y1, :]
        if not band_opaque.any():
            continue

        # MAXCOVERAGE, not k-means, for the per-band step too: k-means (even
        # run on just this band's pixels) is still population-greedy and was
        # empirically observed to drop the eyes even when band-restricted -
        # MAXCOVERAGE is what's proven (§ above) to keep small-but-present
        # colors like the eyes their own slot.
        band_strip = Image.fromarray(rgb_arr[band_y0:band_y1, :].astype(np.uint8), mode="RGB")
        distinct = np.unique(rgb_arr[band_y0:band_y1, :][band_opaque], axis=0)
        k = max(1, min(colors_per_band, len(distinct)))
        band_quantized = band_strip.quantize(colors=k, method=Image.Quantize.MAXCOVERAGE, dither=Image.Dither.NONE)
        band_quantized_rgb = np.array(band_quantized.convert("RGB"), dtype=np.float64)

        band_colors = band_quantized_rgb[band_opaque]
        distinct_out, counts_out = np.unique(band_colors, axis=0, return_counts=True)
        for color, weight in zip(distinct_out, counts_out):
            candidates.append((color, float(weight)))

    merged = _merge_close_candidates(candidates, merge_distance=24.0)
    reduced = _reduce_to_k(merged, colors)
    palette = np.stack([rgb for rgb, _ in reduced])

    pys, pxs = np.where(opaque)
    pixel_rgb = rgb_arr[pys, pxs]
    dists = np.linalg.norm(pixel_rgb[:, None, :] - palette[None, :, :], axis=2)
    nearest = np.argmin(dists, axis=1)
    out[pys, pxs, :3] = np.clip(palette[nearest], 0, 255).round().astype(np.uint8)
    out[pys, pxs, 3] = 255

    return Image.fromarray(out, mode="RGBA")


def fix_color_conflation(
    quantized: Image.Image,
    pre_quantize_source: Image.Image,
    min_y_gap_ratio: float = 0.3,
    min_region_pixels: int = 3,
) -> Image.Image:
    """Stage 4.5 (new, added after a real bug report). quantize_colors() assigns
    each pixel to its nearest color in RGB space with NO awareness of which body
    part it belongs to. Verified empirically: a dark reddish eye-shadow tone and
    the character's separately dark-brown shoes were close enough in RGB space
    to land in the same quantized color, so the eye's color visibly "appeared"
    on the shoes despite them being unrelated, far-apart features (reported by
    user, reproduced at grid=64, colors=10 - docs/design/02-conversion-pipeline.md §4).

    Two earlier approaches were tried and reverted before this one (see that
    section for the full history): reassigning the minority region to its
    neighbors' color erased important small features like the eyes instead of
    separating them; per-connected-component splitting fragmented the palette
    into dozens of near-duplicate colors instead of one clean split.

    This version: for each quantized color whose total vertical span (max Y -
    min Y among its pixels) is suspiciously large, find the single biggest
    vertical gap in its row usage and split there into an "upper" and "lower"
    group. If both groups are non-trivial in size, the smaller group is
    recolored to its own true average color, recovered from
    `pre_quantize_source` (the stage-3 downsampled image, same dimensions,
    still has the real distinct colors before they got collapsed together).
    At most one new color is introduced per conflated color, and a color used
    at a similar height throughout (e.g. both eyes, a jacket's shared trim) is
    left untouched since its vertical span won't exceed the threshold.
    """
    arr = np.array(quantized.convert("RGBA"))
    h, w = arr.shape[:2]
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]
    opaque = alpha > 0
    source_rgb = np.array(pre_quantize_source.convert("RGB"), dtype=np.float64)

    out = arr.copy()
    unique_colors = np.unique(rgb[opaque], axis=0)

    for color in unique_colors:
        mask = np.all(rgb == color, axis=-1) & opaque
        ys = np.where(mask.any(axis=1))[0]
        if len(ys) < 2 or mask.sum() < min_region_pixels * 2:
            continue

        if ys.max() - ys.min() <= h * min_y_gap_ratio:
            continue  # not spread out vertically enough to be a conflation concern

        row_gaps = np.diff(ys)
        split_row_idx = int(np.argmax(row_gaps))
        split_y = (ys[split_row_idx] + ys[split_row_idx + 1]) / 2

        upper_mask = mask.copy()
        upper_mask[int(split_y) + 1 :, :] = False
        lower_mask = mask & ~upper_mask

        if upper_mask.sum() < min_region_pixels or lower_mask.sum() < min_region_pixels:
            continue  # one side is negligible - not worth introducing a new color for

        minority_mask = lower_mask if lower_mask.sum() <= upper_mask.sum() else upper_mask
        true_color = source_rgb[minority_mask].mean(axis=0)
        out[:, :, :3][minority_mask] = np.clip(true_color, 0, 255).round().astype(np.uint8)

    return Image.fromarray(out, mode="RGBA")


def fix_stray_band_pixels(
    quantized: Image.Image,
    pre_quantize_source: Image.Image,
    bands: int = 5,
    dominance_ratio: float = 4.0,
    max_stray_pixels: int = 2,
) -> Image.Image:
    """Stage 4.5 equivalent for palette_source-driven views (docs/design/
    06-multi-angle-input.md §5), added after a real user report: introducing a
    diagonal view produced stray pixels of a small facial-highlight color
    (e.g. a cheek/blush tone) on the torso, far from the face where that
    color actually belongs.

    quantize_colors()'s palette_source path snaps every pixel to its nearest
    color in the shared, front-derived palette purely by RGB distance, with
    no spatial awareness at all. Because a diagonal view is a separately
    rendered image (not a transform of the front one), a torso/jacket pixel's
    true color can differ just enough from the front render that it lands
    closer to a small, unrelated palette entry than to any jacket/outline
    color - producing an isolated wrong-colored pixel.

    fix_color_conflation() (above) looks like the same problem but can't be
    reused here unmodified, for two reasons verified empirically (grid_size in
    (32, 64) x colors in (6, 8, 10) against a real reported case):
      1. It recolors the minority region with pre_quantize_source's raw true
         average, which can introduce a color outside the shared palette -
         exactly the "13 vs 20 colors" drift bug that made pipeline.py gate it
         to palette_source is None in the first place (see convert()).
      2. Its trigger (single largest vertical row-gap, span > 30% of height)
         is too coarse for this: many legitimately tall single-color regions
         (e.g. a jacket spanning shoulder to waist, interrupted by a couple of
         rows of a seam/highlight) get flagged as "conflated" too, which would
         risk introducing new, visible discontinuities that were not there
         before.

    This version reuses quantize_colors()'s own body-part proxy - horizontal
    `bands` (head/neck/torso/legs/feet) - instead of a raw row-gap: for each
    color, find its "home" band (most pixels). A stray is only flagged when
    there is exactly one OTHER band containing that color, it is at least 2
    bands from home (i.e. not merely adjacent, like a natural collar/shoulder
    edge), it holds at most `max_stray_pixels`, and home clearly dominates it
    (>= `dominance_ratio`x). Requiring exactly one other band (not several) is
    what keeps this from firing on a color legitimately reused in small
    amounts everywhere by design (e.g. a shared dark outline/shadow tone, or a
    single highlight white reused as small trim dots across the body) -
    those spread across 3+ bands and are correctly left alone.

    Flagged stray pixels are reassigned to the nearest color ALREADY present
    in `quantized` (using pre_quantize_source's true color at those pixels to
    pick which one, but never introducing a new RGB value) - this guarantees
    every non-front view's palette stays an exact subset of the shared one.
    """
    arr = np.array(quantized.convert("RGBA"))
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]
    opaque = alpha > 0
    out = arr.copy()

    rows_used = np.where(opaque.any(axis=1))[0]
    if len(rows_used) == 0:
        return quantized

    y0, y1 = int(rows_used.min()), int(rows_used.max())
    band_height = max(1.0, (y1 - y0 + 1) / bands)
    source_rgb = np.array(pre_quantize_source.convert("RGB"), dtype=np.float64)

    py, px = np.where(opaque)
    band_of_pixel = np.minimum(bands - 1, ((py - y0) / band_height).astype(int))

    unique_colors = np.unique(rgb[opaque], axis=0)

    for color in unique_colors:
        color_mask = np.all(rgb == color, axis=-1) & opaque
        bands_here = band_of_pixel[color_mask[py, px]]
        band_counts = np.bincount(bands_here, minlength=bands)
        nonzero = np.nonzero(band_counts)[0]
        if len(nonzero) != 2:
            continue

        if band_counts[nonzero[0]] >= band_counts[nonzero[1]]:
            home_idx, stray_idx = nonzero[0], nonzero[1]
        else:
            home_idx, stray_idx = nonzero[1], nonzero[0]
        home_count, stray_count = int(band_counts[home_idx]), int(band_counts[stray_idx])

        if abs(int(home_idx) - int(stray_idx)) < 2:
            continue
        if stray_count > max_stray_pixels or home_count < dominance_ratio * stray_count:
            continue

        band_lo = y0 + int(stray_idx * band_height)
        band_hi = y0 + int((stray_idx + 1) * band_height) if stray_idx < bands - 1 else y1 + 1
        stray_mask = color_mask.copy()
        stray_mask[:band_lo, :] = False
        stray_mask[band_hi:, :] = False

        other_colors = unique_colors[~np.all(unique_colors == color, axis=1)]
        if len(other_colors) == 0:
            continue
        true_color = source_rgb[stray_mask].mean(axis=0)
        dists = np.linalg.norm(other_colors.astype(np.float64) - true_color, axis=1)
        out[:, :, :3][stray_mask] = other_colors[np.argmin(dists)]

    return Image.fromarray(out, mode="RGBA")
