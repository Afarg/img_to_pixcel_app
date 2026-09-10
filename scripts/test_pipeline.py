"""Manual smoke test for app/pipeline.py - run after make_test_image.py.

    .venv/Scripts/python.exe scripts/make_test_image.py
    .venv/Scripts/python.exe scripts/test_pipeline.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from app import pipeline

INPUT = Path(__file__).parent / "sample_input.png"
OUT_DIR = Path(__file__).parent.parent / "output" / "smoke-test"


def main():
    if not INPUT.exists():
        print(f"missing {INPUT} - run make_test_image.py first")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.open(INPUT).convert("RGB")

    t0 = time.time()
    result = pipeline.convert(img, grid_size=16, colors=6, output_size=64, outline=True)
    elapsed = time.time() - t0

    result.pre.save(OUT_DIR / "front.pre.png")
    result.final.save(OUT_DIR / "front.png")

    # diagnostics
    final_colors = result.final.convert("RGBA").getcolors(maxcolors=1_000_000)
    non_transparent_colors = {c for count, c in final_colors if c[3] > 0}
    alpha = result.final.split()[-1]
    opaque_ratio = sum(1 for p in alpha.getdata() if p > 0) / (result.final.width * result.final.height)

    print(f"elapsed: {elapsed:.2f}s")
    print(f"pre size: {result.pre.size}")
    print(f"final size: {result.final.size}")
    print(f"crop_info: box={result.crop_info.crop_box} scale={result.crop_info.scale:.3f}")
    print(f"distinct non-transparent colors in final: {len(non_transparent_colors)} (target ~6 + outline color)")
    print(f"opaque pixel ratio: {opaque_ratio:.2%}")
    print(f"wrote {OUT_DIR / 'front.png'} and {OUT_DIR / 'front.pre.png'}")


if __name__ == "__main__":
    main()
