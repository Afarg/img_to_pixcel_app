"""FastAPI app (docs/design/01-architecture.md §2). Minimal preview UI:
upload up to 5 angle images (front required; diagonal_left/diagonal_right/side/back
optional, docs/design/06-multi-angle-input.md §2-3), see each angle's pixel-art
result, and get a character asset bundle (§6) once more than one angle is provided.
"""

from __future__ import annotations

import io
import json
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from app import pipeline

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output" / "jobs"
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="PixelForge (仮称)")
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")

# docs/design/06-multi-angle-input.md §2: view order matters only for the
# phase label below - processing order is front first (so its palette exists
# before the others need it), then whichever optional views were provided.
# diagonal_left/diagonal_right (rather than a single "diagonal") let
# left-right asymmetric characters supply an accurate image for each side
# instead of relying on a horizontal-flip stand-in (06-multi-angle-input.md
# update history, 2026-07-29).
OPTIONAL_VIEWS = ("diagonal_left", "diagonal_right", "side", "back")
DIAGONAL_VIEWS = ("diagonal_left", "diagonal_right")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


def _phase_for(provided_optional: set[str]) -> tuple[str, str]:
    if "side" in provided_optional or "back" in provided_optional:
        return "phase3", "フェーズ3（正面+斜め+横向き+後ろ向き・フル）"
    if provided_optional & set(DIAGONAL_VIEWS):
        return "phase2", "フェーズ2（正面+斜め・推奨構成）"
    return "phase1", "フェーズ1（正面のみ・最小構成）"


async def _load_image(upload: UploadFile | None) -> Image.Image | None:
    if upload is None or not upload.filename:
        return None
    raw = await upload.read()
    return Image.open(io.BytesIO(raw)).convert("RGB")


@app.post("/api/convert")
async def convert(
    front: UploadFile,
    diagonal_left: UploadFile | None = File(None),
    diagonal_right: UploadFile | None = File(None),
    side: UploadFile | None = File(None),
    back: UploadFile | None = File(None),
    grid_size: int = Form(32),
    colors: int = Form(8),
    output_size: int = Form(64),
    outline: bool = Form(True),
):
    try:
        images = {
            "front": await _load_image(front),
            "diagonal_left": await _load_image(diagonal_left),
            "diagonal_right": await _load_image(diagonal_right),
            "side": await _load_image(side),
            "back": await _load_image(back),
        }
    except Exception:
        return JSONResponse({"ok": False, "error": "画像として読み込めませんでした（PNG/JPGを指定してください）"}, status_code=400)

    provided_optional = {name for name in OPTIONAL_VIEWS if images[name] is not None}
    phase, phase_label = _phase_for(provided_optional)

    job_id = uuid.uuid4().hex[:12]
    job_dir = OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    results: dict[str, pipeline.ConversionResult] = {}
    try:
        results["front"] = pipeline.convert(
            images["front"], grid_size=grid_size, colors=colors, output_size=output_size, outline=outline
        )
        for view_name in OPTIONAL_VIEWS:
            if images[view_name] is None:
                continue
            results[view_name] = pipeline.convert(
                images[view_name],
                grid_size=grid_size,
                colors=colors,
                output_size=output_size,
                outline=outline,
                palette_source=results["front"].quantized_reference,
            )
    except pipeline.UnsupportedPoseError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:  # noqa: BLE001 - surface unexpected errors to the UI rather than a bare 500
        return JSONResponse({"ok": False, "error": f"変換中にエラーが発生しました: {e}"}, status_code=500)
    elapsed = time.time() - t0

    manifest_views = {}
    response_views = {}
    for view_name, result in results.items():
        result.final.save(job_dir / f"{view_name}.png")
        result.pre.save(job_dir / f"{view_name}.pre.png")
        manifest_views[view_name] = {
            "final": f"{view_name}.png",
            "pre": f"{view_name}.pre.png",
            "scale": result.crop_info.scale,
            "cropBox": list(result.crop_info.crop_box),
        }
        response_views[view_name] = {
            "preUrl": f"/output/{job_id}/{view_name}.pre.png",
            "finalUrl": f"/output/{job_id}/{view_name}.png",
            "finalSize": list(result.final.size),
        }

    manifest = {
        "characterId": job_id,
        "gridSize": grid_size,
        "outputSize": output_size,
        "colors": colors,
        "views": manifest_views,
    }
    (job_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    bundle_zip_url = None
    if len(results) > 1:
        # docs/design/06-multi-angle-input.md §6: a bundle is only meaningful
        # once there's more than the front view - phase 1 just uses front.png
        # directly (§7), no bundle needed.
        zip_path = job_dir / "bundle.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for entry in job_dir.iterdir():
                if entry.name != "bundle.zip":
                    zf.write(entry, arcname=entry.name)
        bundle_zip_url = f"/output/{job_id}/bundle.zip"

    return JSONResponse(
        {
            "ok": True,
            "jobId": job_id,
            "elapsedSeconds": round(elapsed, 2),
            "phase": phase,
            "phaseLabel": phase_label,
            "views": response_views,
            "manifestUrl": f"/output/{job_id}/manifest.json",
            "bundleZipUrl": bundle_zip_url,
        }
    )
