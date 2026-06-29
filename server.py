"""Local web UI for PNG -> SVG conversion."""

from __future__ import annotations

import base64
import json
import queue
import threading
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from convert import (
    DEFAULT_SMOOTHING,
    OUTPUT_FORMATS,
    RASTER_MIME_TYPES,
    SVG_MODES,
    SMOOTHING_PRESETS,
    convert_embedded_svg_bytes,
    convert_image_bytes,
    convert_raster_image_bytes,
    detect_optimizer,
    list_part_types,
    load_recipes,
)

from svg_analyze import analyze_svg
from svg_analyze.correction_memory import list_corrections, save_corrections_batch
from svg_analyze.export.write_game_manifest import resolve_game_root, write_sheet_manifest

ROOT = Path(__file__).parent
WEB_DIR = ROOT / "web"

app = FastAPI(title="SVG Asset Pipeline", version="1.0.0")
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".heif"}
SVG_SUFFIXES = {".svg"}
IMAGE_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".heic": "image/heic",
    ".heif": "image/heif",
}


class ZipFileItem(BaseModel):
    filename: str
    format: str | None = None
    svg: str | None = None
    dataBase64: str | None = None


class ZipExportRequest(BaseModel):
    files: list[ZipFileItem] = Field(min_length=1)


class CorrectionItem(BaseModel):
    frameIndex: int
    targetType: str
    targetId: str
    before: dict | list | str | float | int | None = None
    after: dict | list | str | float | int | None = None
    reason: str | None = None


class CorrectionBatchRequest(BaseModel):
    assetId: str = Field(min_length=1)
    corrections: list[CorrectionItem] = Field(min_length=1)


def _upload_suffix(file: UploadFile, default_name: str, default_suffix: str) -> str:
    return Path(file.filename or default_name).suffix.lower() or default_suffix


async def _read_upload_bytes(
    file: UploadFile,
    *,
    default_name: str,
    default_suffix: str,
    allowed_suffixes: set[str],
) -> tuple[str, bytes]:
    suffix = _upload_suffix(file, default_name, default_suffix)
    if suffix not in allowed_suffixes:
        raise HTTPException(status_code=400, detail=f"Định dạng không hỗ trợ: {suffix}")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="File rỗng.")
    return suffix, payload


async def _read_svg_upload(file: UploadFile) -> tuple[str, str]:
    _suffix, svg_bytes = await _read_upload_bytes(
        file,
        default_name="input.svg",
        default_suffix=".svg",
        allowed_suffixes=SVG_SUFFIXES,
    )
    try:
        return file.filename or "input.svg", svg_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="SVG phải là UTF-8 text.") from exc


def _analyze_svg_request(
    svg_text: str,
    source_file: str,
    *,
    ml_landmarks: bool,
    mmpose: bool,
    focus_frames: list[int] | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict:
    try:
        return analyze_svg(
            svg_text,
            source_file,
            enable_ml_landmarks=ml_landmarks or None,
            enable_mmpose=mmpose or None,
            focus_frames=focus_frames,
            progress=progress,
        )
    except ET.ParseError as exc:
        raise HTTPException(status_code=400, detail=f"SVG không hợp lệ: {exc}") from exc


def _parse_focus_frames(raw: str) -> list[int]:
    frames: list[int] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            frame_index = int(token)
        except ValueError:
            continue
        if frame_index >= 0 and frame_index not in frames:
            frames.append(frame_index)
    return frames


def _ndjson(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _preview_data_url(image_bytes: bytes, suffix: str) -> str:
    mime = IMAGE_MIME_BY_SUFFIX.get(suffix, f"image/{suffix.lstrip('.')}")
    preview_b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{preview_b64}"


def _data_url(payload: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"


def _canonical_export_extension(format_name: str | None, filename: str, *, is_svg: bool) -> str:
    if is_svg:
        return ".svg"
    normalized = (format_name or Path(filename).suffix.lstrip(".") or "bin").lower()
    if normalized == "jpg":
        return ".jpg"
    if normalized == "jpeg":
        return ".jpeg"
    if normalized in RASTER_MIME_TYPES:
        return f".{normalized}"
    suffix = Path(filename).suffix.lower()
    return suffix or ".bin"


def _export_filename(filename: str, format_name: str | None, *, is_svg: bool) -> str:
    stem = Path(filename).stem or "asset"
    return f"{stem}{_canonical_export_extension(format_name, filename, is_svg=is_svg)}"


def _unique_export_name(filename: str, used_names: set[str]) -> str:
    stem = Path(filename).stem or "asset"
    suffix = Path(filename).suffix or ".bin"
    name = f"{stem}{suffix}"
    counter = 2
    while name in used_names:
        name = f"{stem}-{counter}{suffix}"
        counter += 1
    used_names.add(name)
    return name


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/analyze")
def analyze_page() -> FileResponse:
    return FileResponse(WEB_DIR / "analyze.html")


@app.get("/api/meta")
def meta() -> dict:
    recipes = load_recipes()
    return {
        "parts": list_part_types(recipes),
        "optimizer": detect_optimizer(),
        "outputTypes": list(OUTPUT_FORMATS),
        "svgModes": list(SVG_MODES),
        "defaultRecipe": recipes.get("default") or {},
        "smoothingLevels": list(SMOOTHING_PRESETS.keys()),
        "defaultSmoothing": DEFAULT_SMOOTHING,
        "analyze": {
            "defaultGameRoot": str(resolve_game_root(None)),
            "features": {
                "mlLandmarks": True,
                "mmpose": True,
                "gameManifestExport": True,
            },
        },
    }


@app.post("/api/convert")
async def convert(
    file: UploadFile = File(...),
    part: str = Form("default"),
    output_type: str = Form("svg"),
    svg_mode: str = Form("embedded"),
    smoothing: str = Form(DEFAULT_SMOOTHING),
    color_precision: int = Form(0),
    sharpness: int = Form(0),
    remove_bg: bool = Form(False),
    trim: bool = Form(False),
) -> dict:
    output_type = output_type.lower()
    if output_type not in OUTPUT_FORMATS:
        raise HTTPException(status_code=400, detail=f"Định dạng output không hỗ trợ: {output_type}")
    if svg_mode not in SVG_MODES:
        raise HTTPException(status_code=400, detail=f"Kiểu SVG không hỗ trợ: {svg_mode}")

    if smoothing not in SMOOTHING_PRESETS:
        raise HTTPException(status_code=400, detail=f"Mức làm mịn không hợp lệ: {smoothing}")

    suffix, image_bytes = await _read_upload_bytes(
        file,
        default_name="input.png",
        default_suffix=".png",
        allowed_suffixes=ALLOWED_SUFFIXES,
    )

    if output_type == "svg":
        if svg_mode == "embedded":
            try:
                svg, params, optimizer, elapsed = convert_embedded_svg_bytes(
                    image_bytes,
                    remove_bg=remove_bg,
                    trim=trim,
                )
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc

            return {
                "filename": Path(file.filename or "asset").stem + ".svg",
                "extension": "svg",
                "format": "svg",
                "svg": svg,
                "params": params,
                "optimizer": optimizer,
                "elapsed": round(elapsed, 2),
                "previewDataUrl": _preview_data_url(image_bytes, suffix),
                "sizeBytes": len(svg.encode("utf-8")),
            }

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

        return {
            "filename": Path(file.filename or "asset").stem + ".svg",
            "extension": "svg",
            "format": "svg",
            "svg": svg,
            "params": params,
            "optimizer": optimizer,
            "elapsed": round(elapsed, 2),
            "previewDataUrl": _preview_data_url(image_bytes, suffix),
            "sizeBytes": len(svg.encode("utf-8")),
        }

    try:
        payload, params, mime, extension, elapsed = convert_raster_image_bytes(
            image_bytes,
            output_type=output_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    data_base64 = base64.b64encode(payload).decode("ascii")
    return {
        "filename": f"{Path(file.filename or 'asset').stem}.{extension}",
        "extension": extension,
        "format": output_type,
        "mime": mime,
        "dataBase64": data_base64,
        "dataUrl": f"data:{mime};base64,{data_base64}",
        "params": params,
        "optimizer": "none",
        "elapsed": round(elapsed, 2),
        "previewDataUrl": _preview_data_url(image_bytes, suffix),
        "sizeBytes": len(payload),
    }


@app.post("/api/export-zip")
def export_zip(payload: ZipExportRequest) -> StreamingResponse:
    buf = BytesIO()
    used_names: set[str] = set()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in payload.files:
            if item.svg:
                name = _unique_export_name(
                    _export_filename(item.filename, item.format, is_svg=True),
                    used_names,
                )
                archive.writestr(name, item.svg.encode("utf-8"))
            elif item.dataBase64:
                name = _unique_export_name(
                    _export_filename(item.filename, item.format, is_svg=False),
                    used_names,
                )
                archive.writestr(name, base64.b64decode(item.dataBase64))
            else:
                raise HTTPException(status_code=400, detail=f"File thiếu dữ liệu: {item.filename}")

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="image-export.zip"'},
    )


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    ml_landmarks: bool = Form(False),
    mmpose: bool = Form(False),
) -> dict:
    source_file, svg_text = await _read_svg_upload(file)
    try:
        return _analyze_svg_request(
            svg_text,
            source_file,
            ml_landmarks=ml_landmarks,
            mmpose=mmpose,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/analyze-stream")
async def analyze_stream(
    file: UploadFile = File(...),
    ml_landmarks: bool = Form(False),
    mmpose: bool = Form(False),
    focus_frames: str = Form(""),
) -> StreamingResponse:
    source_file, svg_text = await _read_svg_upload(file)
    focus_frame_indices = _parse_focus_frames(focus_frames)

    def stream() -> object:
        events: queue.Queue[dict[str, Any]] = queue.Queue()

        def progress(event: dict[str, Any]) -> None:
            events.put({"type": "log", **event})

        def worker() -> None:
            try:
                result = _analyze_svg_request(
                    svg_text,
                    source_file,
                    ml_landmarks=ml_landmarks,
                    mmpose=mmpose,
                    focus_frames=focus_frame_indices or None,
                    progress=progress,
                )
                events.put({"type": "result", "result": result})
            except HTTPException as exc:
                events.put({"type": "error", "statusCode": exc.status_code, "detail": exc.detail})
            except Exception as exc:  # noqa: BLE001 — preserve current API error behavior in stream form
                events.put({"type": "error", "statusCode": 500, "detail": str(exc)})

        focus_text = f" · focus frames {', '.join(str(i) for i in focus_frame_indices)}" if focus_frame_indices else ""
        events.put({"type": "log", "step": "queue", "message": f"Queued analysis for {source_file}{focus_text}", "elapsedMs": 0})
        thread = threading.Thread(target=worker, name=f"analyze-{source_file}", daemon=True)
        thread.start()

        while True:
            event = events.get()
            yield _ndjson(event)
            if event.get("type") in {"result", "error"}:
                break

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/export-game-manifest")
async def export_game_manifest(
    file: UploadFile = File(...),
    game_root: str = Form(""),
    asset_path: str = Form(""),
    ml_landmarks: bool = Form(False),
    mmpose: bool = Form(False),
) -> dict:
    source_file, svg_text = await _read_svg_upload(file)
    try:
        analysis = _analyze_svg_request(
            svg_text,
            source_file,
            ml_landmarks=ml_landmarks,
            mmpose=mmpose,
        )
        rel = asset_path.strip() or source_file
        svg_path = Path(rel)
        root = resolve_game_root(game_root or None)
        out_path = write_sheet_manifest(analysis, svg_path, game_root=root)
        return {
            "written": str(out_path),
            "gameRoot": str(root),
            "assetPath": rel,
            "gameManifest": analysis.get("gameManifest"),
            "stackRecommendation": analysis.get("stackRecommendation"),
            "analysis": analysis,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ET.ParseError as exc:
        raise HTTPException(status_code=400, detail=f"SVG không hợp lệ: {exc}") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot write manifest: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/corrections")
def save_corrections(payload: CorrectionBatchRequest) -> dict:
    try:
        items = [item.model_dump() for item in payload.corrections]
        return save_corrections_batch(payload.assetId, items)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot save corrections: {exc}") from exc


@app.get("/api/corrections/{asset_id}")
def get_corrections(asset_id: str) -> dict:
    return list_corrections(asset_id)


def main() -> None:
    import os

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8765"))
    uvicorn.run("server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
