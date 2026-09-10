"""Manually builds a character asset bundle (docs/design/06-multi-angle-input.md §6)
for ani_convert_app to test against, since the multi-angle bundle UI/API isn't
implemented yet. Phase 1 (front only) test case.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from PIL import Image

from app import pipeline

INPUT = Path(__file__).parent / "real_sample_standing.png"
BUNDLE_DIR = Path(__file__).resolve().parent.parent.parent / "ani_convert_app" / "scripts" / "test_bundle_phase1"


def main():
    img = Image.open(INPUT).convert("RGB")
    result = pipeline.convert(img, grid_size=32, colors=8, output_size=64, outline=True)

    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    result.final.save(BUNDLE_DIR / "front.png")
    result.pre.save(BUNDLE_DIR / "front.pre.png")

    manifest = {
        "characterId": "test-character",
        "gridSize": 32,
        "outputSize": 64,
        "colors": 8,
        "views": {
            "front": {
                "final": "front.png",
                "pre": "front.pre.png",
                "scale": result.crop_info.scale,
                "cropBox": list(result.crop_info.crop_box),
            }
        },
    }
    (BUNDLE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote bundle to {BUNDLE_DIR}")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
