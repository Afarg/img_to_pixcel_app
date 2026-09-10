"""Regression check for the background_removal.py alpha-confidence fix
(2026-08-16, docs/project-status.md): re-runs the original 4 test characters
(imgs1/, wizard/shrine/scarf/spirit) through all 12 CLAUDE.md-mandated
patterns to confirm the fix (which changes stage 1 for EVERY character, not
just business-character-c) doesn't regress a completely different, more
varied character set.
"""

import json
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import pipeline  # noqa: E402

SRC_DIR = Path(r"D:\app\agents_app\img\imgs1")
OUT_DIR = Path(r"D:\app\agents_app\img_to_pixcel_app\output\test-characters-regression")

CHARACTERS = {
    "char_a_wizard": "char_a_wizard.png",
    "char_b_shrine": "char_b_shrine.png",
    "char_c_scarf": "char_c_scarf.png",
    "char_d_spirit": "char_d_spirit.png",
}

GRID_SIZES = (32, 64, 128)
COLORS = (8, 10)
OUTPUT_SIZES = (64, 128)


def opaque_ratio(img: Image.Image) -> float:
    alpha = img.split()[-1]
    px = list(alpha.getdata())
    return round(sum(1 for a in px if a > 0) / len(px), 4)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for char_name, filename in CHARACTERS.items():
        image = Image.open(SRC_DIR / filename).convert("RGB")
        char_out_dir = OUT_DIR / char_name
        char_out_dir.mkdir(parents=True, exist_ok=True)
        for grid_size in GRID_SIZES:
            for colors in COLORS:
                for output_size in OUTPUT_SIZES:
                    t0 = time.time()
                    entry = {"character": char_name, "grid_size": grid_size, "colors": colors, "output_size": output_size}
                    try:
                        result = pipeline.convert(image, grid_size=grid_size, colors=colors, output_size=output_size)
                        out_path = char_out_dir / f"g{grid_size}_c{colors}_o{output_size}.png"
                        result.final.save(out_path)
                        entry.update(
                            {
                                "ok": True,
                                "elapsed_sec": round(time.time() - t0, 2),
                                "opaque_ratio": opaque_ratio(result.final),
                                "output": str(out_path),
                            }
                        )
                    except Exception as e:  # noqa: BLE001
                        entry.update({"ok": False, "error": f"{type(e).__name__}: {e}"})
                    results.append(entry)
                    print(f"{char_name} g{grid_size}_c{colors}_o{output_size}: {'OK' if entry['ok'] else 'FAIL - ' + entry.get('error', '')}")

    (OUT_DIR / "report.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    n_ok = sum(1 for r in results if r["ok"])
    print(f"\n{n_ok}/{len(results)} patterns OK.")
    if n_ok != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
