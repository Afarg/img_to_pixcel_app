import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from app import pipeline

INPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "sample_input.png"
OUT_DIR = Path(__file__).parent.parent / "output" / "debug-stages"
OUT_DIR.mkdir(parents=True, exist_ok=True)

VIEW_SIZE = 512


def save(img, name):
    img.save(OUT_DIR / name)
    # also save a big nearest-neighbor upscaled copy purely for human inspection
    view = img.resize((VIEW_SIZE, VIEW_SIZE), resample=Image.NEAREST)
    # composite onto a checkerboard so transparent vs. opaque is visible
    checker = Image.new("RGB", (VIEW_SIZE, VIEW_SIZE))
    for y in range(0, VIEW_SIZE, 16):
        for x in range(0, VIEW_SIZE, 16):
            shade = 200 if (x // 16 + y // 16) % 2 == 0 else 150
            checker.paste((shade, shade, shade), (x, y, x + 16, y + 16))
    checker.paste(view, (0, 0), view if view.mode == "RGBA" else None)
    checker.save(OUT_DIR / f"view_{name}")
    print(f"{name}: mode={img.mode} size={img.size}")


def main():
    img = Image.open(INPUT).convert("RGB")
    removed = pipeline.remove_background(img)
    save(removed, "1_removed.png")

    pre, crop_box = pipeline.crop_and_center(removed)
    save(pre, "2_cropped.png")

    small = pipeline.downsample(pre, grid_size=16)
    save(small, "3_downsampled.png")

    quantized = pipeline.quantize_colors(small, colors=6)
    save(quantized, "4_quantized.png")

    outlined = pipeline.add_outline(quantized)
    save(outlined, "5_outlined.png")

    final = pipeline.upscale(outlined, output_size=64)
    save(final, "6_final.png")


if __name__ == "__main__":
    main()
