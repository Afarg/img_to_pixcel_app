"""CLAUDE.md必須ルール: convert()の12パターン検証(grid_size 32/64/128 x colors 8/10 x
output_size 64/128)を、新規ビジネスキャラクター4体(docs/prompt/business-characters-generation-prompts.md)
に対して実行する。参考: 前回のtest-characters検証(docs/project-status.md §10.1)と同じ形式でreport.jsonを出力。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import pipeline  # noqa: E402

SRC_DIR = Path(r"D:\app\agents_app\img\imgs2")
OUT_DIR = Path(r"D:\app\agents_app\img_to_pixcel_app\output\business-characters")

CHARACTERS = {
    "char_a_male_navy": "Firefly_Gemini Flash_chibi anime character, full body, standing straight, facing forward,_both arms relaxe 704841.png",
    "char_b_male_gray": "Firefly_Gemini Flash_chibi anime character, full body, standing straight, facing forward,_both arms relaxe 704841 (1).png",
    "char_c_female_casual": "Firefly_Gemini Flash_chibi anime character, full body, standing straight, facing forward,_both arms relaxe 704841 (2).png",
    "char_d_female_pantsuit": "Firefly_Gemini Flash_chibi anime character, full body, standing straight, facing forward,_both arms relaxe 704841 (3).png",
}

GRID_SIZES = (32, 64, 128)
COLORS = (8, 10)
OUTPUT_SIZES = (64, 128)


def opaque_ratio(img: Image.Image) -> float:
    alpha = img.split()[-1]
    px = list(alpha.getdata())
    return round(sum(1 for a in px if a > 0) / len(px), 4)


def distinct_colors(img: Image.Image) -> int:
    px = img.convert("RGBA").getdata()
    return len({p for p in px if p[3] > 0})


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for char_name, filename in CHARACTERS.items():
        src_path = SRC_DIR / filename
        image = Image.open(src_path).convert("RGB")
        char_out_dir = OUT_DIR / char_name
        char_out_dir.mkdir(parents=True, exist_ok=True)
        for grid_size in GRID_SIZES:
            for colors in COLORS:
                for output_size in OUTPUT_SIZES:
                    t0 = time.time()
                    entry = {
                        "character": char_name,
                        "grid_size": grid_size,
                        "colors": colors,
                        "output_size": output_size,
                    }
                    try:
                        result = pipeline.convert(
                            image,
                            grid_size=grid_size,
                            colors=colors,
                            output_size=output_size,
                        )
                        out_path = char_out_dir / f"g{grid_size}_c{colors}_o{output_size}.png"
                        result.final.save(out_path)
                        entry.update(
                            {
                                "ok": True,
                                "elapsed_sec": round(time.time() - t0, 2),
                                "distinct_colors": distinct_colors(result.final),
                                "opaque_ratio": opaque_ratio(result.final),
                                "output": str(out_path),
                            }
                        )
                    except Exception as e:  # noqa: BLE001
                        entry.update({"ok": False, "error": f"{type(e).__name__}: {e}"})
                    results.append(entry)
                    print(
                        f"{char_name} g{grid_size}_c{colors}_o{output_size}: "
                        f"{'OK' if entry['ok'] else 'FAIL - ' + entry.get('error', '')}"
                    )

    report_path = OUT_DIR / "report.json"
    report_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    n_ok = sum(1 for r in results if r["ok"])
    print(f"\n{n_ok}/{len(results)} patterns OK. Report: {report_path}")
    if n_ok != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
