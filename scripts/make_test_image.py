"""Generates a synthetic test photo (character-on-background) for smoke-testing
the pipeline when a real photo isn't available. Not a substitute for testing
with a real photo - see docs/design/04-constraints-and-limitations.md §2
(background-removal accuracy on real photos is a separate, unverified question).
"""

from PIL import Image, ImageDraw

W, H = 400, 500


def main():
    img = Image.new("RGB", (W, H), (110, 170, 220))  # sky-blue-ish background
    draw = ImageDraw.Draw(img)

    # a "busy" background element so background removal has something to discard
    draw.rectangle([0, 380, W, H], fill=(90, 150, 70))  # ground
    for x in range(0, W, 40):
        draw.line([(x, 380), (x + 15, 340)], fill=(70, 130, 55), width=6)

    # simple humanoid character, off-center so the auto-crop is meaningfully tested
    cx, cy = 260, 260
    draw.ellipse([cx - 45, cy - 130, cx + 45, cy - 40], fill=(240, 200, 170))  # head
    draw.ellipse([cx - 12, cy - 100, cx - 2, cy - 88], fill=(40, 30, 30))  # left eye
    draw.ellipse([cx + 2, cy - 100, cx + 12, cy - 88], fill=(40, 30, 30))  # right eye
    draw.rectangle([cx - 55, cy - 40, cx + 55, cy + 90], fill=(60, 90, 200))  # torso/shirt
    draw.rectangle([cx - 55, cy + 90, cx - 15, cy + 180], fill=(50, 50, 60))  # left leg
    draw.rectangle([cx + 15, cy + 90, cx + 55, cy + 180], fill=(50, 50, 60))  # right leg

    out_path = "scripts/sample_input.png"
    img.save(out_path)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
