"""Local web UI for PNG -> SVG conversion."""

from __future__ import annotations

import base64
import zipfile
from io import BytesIO
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from convert import (
    DEFAULT_SMOOTHING,
    SMOOTHING_PRESETS,
    convert_image_bytes,
    detect_optimizer,
    list_part_types,
    load_recipes,
)

ROOT = Path(__file__).parent
WEB_DIR = ROOT / "web"

app = FastAPI(title="SVG Asset Pipeline", version="1.0.0")
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class ZipFileItem(BaseModel):
    filename: str
    svg: str = Field(min_length=1)


class ZipExportRequest(BaseModel):
    files: list[ZipFileItem] = Field(min_length=1)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/meta")
def meta() -> dict:
    recipes = load_recipes()
    return {
        "parts": list_part_types(recipes),
        "optimizer": detect_optimizer(),
        "defaultRecipe": recipes.get("default") or {},
        "smoothingLevels": list(SMOOTHING_PRESETS.keys()),
        "defaultSmoothing": DEFAULT_SMOOTHING,
    }


@app.post("/api/convert")
async def convert(
    file: UploadFile = File(...),
    part: str = Form("default"),
    smoothing: str = Form(DEFAULT_SMOOTHING),
    color_precision: int = Form(0),
    sharpness: int = Form(0),
    remove_bg: bool = Form(False),
    trim: bool = Form(False),
) -> dict:
    suffix = Path(file.filename or "input.png").suffix.lower() or ".png"
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Định dạng không hỗ trợ: {suffix}")
    if smoothing not in SMOOTHING_PRESETS:
        raise HTTPException(status_code=400, detail=f"Mức làm mịn không hợp lệ: {smoothing}")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="File rỗng.")

    try:
        svg, params, optimizer, elapsed = convert_image_bytes(
            image_bytes,
            part=part,
            suffix=suffix,
            smoothing=smoothing,
            color_precision=color_precision or None,
            sharpness=max(0, min(250, sharpness)),
            remove_bg=remove_bg,
            trim=trim,
        )
    except Exception as exc:  # vtracer may raise various errors
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    preview_b64 = base64.b64encode(image_bytes).decode("ascii")
    mime = "image/png" if suffix == ".png" else f"image/{suffix.lstrip('.')}"
    if suffix in {".jpg", ".jpeg"}:
        mime = "image/jpeg"

    return {
        "filename": Path(file.filename or "asset").stem + ".svg",
        "svg": svg,
        "params": params,
        "optimizer": optimizer,
        "elapsed": round(elapsed, 2),
        "previewDataUrl": f"data:{mime};base64,{preview_b64}",
        "sizeBytes": len(svg.encode("utf-8")),
    }


@app.post("/api/export-zip")
def export_zip(payload: ZipExportRequest) -> StreamingResponse:
    buf = BytesIO()
    used_names: set[str] = set()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in payload.files:
            stem = Path(item.filename).stem or "asset"
            name = f"{stem}.svg"
            counter = 2
            while name in used_names:
                name = f"{stem}-{counter}.svg"
                counter += 1
            used_names.add(name)
            archive.writestr(name, item.svg.encode("utf-8"))

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="svg-export.zip"'},
    )


def main() -> None:
    uvicorn.run("server:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()
