"""Builds phase-1 (front only) character asset bundles for the 4 business
characters (docs/prompt/business-characters-generation-prompts.md), for
ani_convert_app to consume. Same pattern as make_test_bundle.py, but for 4
characters at once, at the dashboard-representative setting
(grid_size=128/colors=10/output_size=128, per docs/project-status.md §11.5's
finding that grid_size=64 loses eye detail on busier hair).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from app import pipeline

SRC_DIR = Path(r"D:\app\agents_app\img\imgs2")
BUNDLE_ROOT = Path(__file__).resolve().parent.parent.parent / "ani_convert_app" / "scripts"

GRID_SIZE = 128
COLORS = 10
OUTPUT_SIZE = 128

CHARACTERS = {
    "business-character-a": "Firefly_Gemini Flash_chibi anime character, full body, standing straight, facing forward,_both arms relaxe 704841.png",
    "business-character-b": "Firefly_Gemini Flash_chibi anime character, full body, standing straight, facing forward,_both arms relaxe 704841 (1).png",
    "business-character-c": "Firefly_Gemini Flash_chibi anime character, full body, standing straight, facing forward,_both arms relaxe 704841 (2).png",
    "business-character-d": "Firefly_Gemini Flash_chibi anime character, full body, standing straight, facing forward,_both arms relaxe 704841 (3).png",
}


def main() -> None:
    for char_id, filename in CHARACTERS.items():
        img = Image.open(SRC_DIR / filename).convert("RGB")
        result = pipeline.convert(img, grid_size=GRID_SIZE, colors=COLORS, output_size=OUTPUT_SIZE, outline=True)

        bundle_dir = BUNDLE_ROOT / char_id.replace("-", "_")
        bundle_dir.mkdir(parents=True, exist_ok=True)
        result.final.save(bundle_dir / "front.png")
        result.pre.save(bundle_dir / "front.pre.png")

        manifest = {
            "characterId": char_id,
            "gridSize": GRID_SIZE,
            "outputSize": OUTPUT_SIZE,
            "colors": COLORS,
            "views": {
                "front": {
                    "final": "front.png",
                    "pre": "front.pre.png",
                    "scale": result.crop_info.scale,
                    "cropBox": list(result.crop_info.crop_box),
                }
            },
        }
        (bundle_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote bundle: {bundle_dir}")


if __name__ == "__main__":
    main()
