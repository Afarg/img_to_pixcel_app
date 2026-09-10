"""Stage 1: subject isolation (docs/design/02-conversion-pipeline.md §2①).

Split out of pipeline.py (2026-07-28) so this stage can be found and fixed on
its own - it's already been the source of one real bug (premultiplied alpha)
and is the most likely place for the next one, since it's the stage that
turns arbitrary user photos into the RGBA data everything downstream trusts.
"""

from __future__ import annotations

import numpy as np
from PIL import Image
from rembg import remove, new_session

_rembg_session = None


def _get_session(model_name: str = "u2netp"):
    global _rembg_session
    if _rembg_session is None or _rembg_session.model_name != model_name:
        _rembg_session = new_session(model_name)
    return _rembg_session


def remove_background(image: Image.Image, model_name: str = "u2netp") -> Image.Image:
    """Returns an RGBA image with the background made transparent.

    Un-premultiplies rembg's output. Found via a user report (real image: a
    character in a white lab coat) and confirmed empirically: rembg's result
    is tagged mode "RGBA" (straight alpha) but the pixel DATA is actually
    alpha-premultiplied - at a low-alpha edge pixel that should be white
    (255,255,255), the raw output was e.g. (10,10,10,10) and (48,49,49,49):
    R≈G≈B≈alpha, exactly the signature of premultiplied color scaled down by
    a small alpha rather than the true (bright) color. Because the PIL mode
    tag says "RGBA" rather than "RGBa" (Pillow's premultiplied-alpha mode),
    nothing downstream would auto-correct this - every later stage would see
    near-black colors at every semi-transparent edge, which is exactly the
    "white coat bleeding black at the edges" symptom that was reported. This
    only becomes glaringly visible for light/white source colors (dark
    colors were already dark, so premultiplied-darkening wasn't obviously
    wrong there) - see docs/design/04-constraints-and-limitations.md §2.
    """
    session = _get_session(model_name)
    result = remove(image.convert("RGB"), session=session).convert("RGBA")

    arr = np.array(result, dtype=np.float64)
    alpha = arr[:, :, 3]
    safe_alpha = np.where(alpha > 0, alpha, 255)  # avoid div-by-zero; fully transparent pixels' color is moot
    unpremultiplied = arr[:, :, :3] * (255.0 / safe_alpha[:, :, None])
    arr[:, :, :3] = np.clip(unpremultiplied, 0, 255)

    # Repair rembg's raw alpha CONFIDENCE (separate problem from the
    # premultiplied-color fix above, found via a real user report: a
    # pale-skinned character's legs came out riddled with holes in the final
    # pixel art). rembg (u2netp) sometimes assigns very low alpha (measured
    # as low as 1/255) across broad interior regions of a subject when it has
    # low contrast against the background (here: pale skin vs. the plain
    # light-gray background these chibi characters are generated on), not
    # just at true edges where a soft alpha ramp is expected. This is
    # invisible in `pre.png` itself (a near-white leg composited at low
    # opacity over a white viewer background still looks near-white), but
    # downsample()'s per-cell max-pool + hard threshold (`alpha_threshold=60`)
    # drops any grid cell whose every source pixel stays under that bar -
    # which a broad low-confidence patch does, unlike the few-pixel-wide edge
    # ramp max-pooling is designed to survive.
    #
    # First attempt: promote any nonzero-alpha pixel to opaque (true
    # background measured exactly 0 in every sample taken) and
    # `binary_fill_holes` the rest. Rejected after measurement: the gap
    # between this same character's two legs turned out to be JUST AS LOW
    # in rembg's raw alpha as the buggy dropout inside each leg (both mostly
    # single-digit values, not a clean 0), so alpha value/topology alone
    # cannot tell a real anatomical gap from a segmentation-confidence
    # failure - that version fused her legs into one solid blob.
    #
    # Second attempt: also require the weak pixel's ORIGINAL (pre-rembg)
    # color to differ from a corner-sampled background reference color by
    # some Euclidean RGB distance. This correctly separated the leg dropout
    # (SOURCE RGB (252,216,196), clearly skin) from the true inter-leg gap
    # (matches the background almost exactly). But tested against 4 OTHER,
    # already-working characters as a regression check, it fired somewhere
    # it shouldn't have: one character's source art has a drawn drop-shadow
    # ellipse under its boots (~154,150,150) that differs from the
    # background by even MORE than plain skin does - raw color distance
    # can't tell "a body part rembg is unsure about" from "genuinely
    # something else that isn't flat background either". A follow-up
    # attempt gating promotion by distance to rembg's own confidently-opaque
    # pixels also failed: the shadow is drawn directly touching the boots in
    # the source art, so its nearest edge is just as close to confident
    # silhouette as the leg dropout is - there's no geometric gap to key off.
    #
    # What DOES separate them: CHROMA (`max(R,G,B) - min(R,G,B)`), not raw
    # color distance. Every character here is generated on a plain, flat,
    # neutral GRAY background (docs/prompt/*-generation-prompts.md §0.1) -
    # measured chroma <=4 in every corner sampled across 6 different source
    # images. A cast shadow on a neutral surface is still neutral, just
    # darker (the wizard's shadow measured chroma=4, essentially identical
    # to plain background) - it fails a chroma test just like real
    # background does. Skin, hair, and colored clothing are never neutral
    # (the leg dropout measured chroma=56) - they clearly pass it. This is
    # the standard color-theory reason shadows read as "the same surface,
    # dimmer" rather than a different color, and it holds regardless of a
    # given character's actual skin/hair/clothing palette, unlike a fixed
    # background-distance threshold. Only misses achromatic (white/gray/
    # black) character material suffering this same failure mode - not
    # observed in testing so far, and out of scope for this fix; flagged in
    # docs/design/04-constraints-and-limitations.md if it comes up.
    WEAK_ALPHA = 60  # matches downsample()'s own alpha_threshold - a grid cell made entirely of
    # pixels this unsure gets dropped regardless of how many of them there are, so this is the
    # exact bar a pixel needs to clear to not risk becoming a hole
    CHROMA_TOLERANCE = 15  # background/shadow chroma measured <=4 in every case checked;
    # real subject colors measured 56 in the reported case - comfortable margin either way

    source_rgb = np.array(image.convert("RGB"), dtype=np.float64)
    chroma = source_rgb.max(axis=-1) - source_rgb.min(axis=-1)
    promote = (alpha < WEAK_ALPHA) & (chroma >= CHROMA_TOLERANCE)

    arr[:, :, :3][promote] = source_rgb[promote]  # use the raw source color, not the unpremultiplied one - reliable at any alpha
    arr[:, :, 3] = np.where(promote, 255, alpha)

    return Image.fromarray(arr.astype(np.uint8), mode="RGBA")
