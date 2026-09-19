from __future__ import annotations

import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

# Bootstrap the current Deep-Live-Cam runtime exactly as its launcher does:
# Windows CUDA DLL discovery and project-root PATH setup happen before importing
# the Deep-Live-Cam modules that create ONNX sessions.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ["PATH"] = str(PROJECT_ROOT) + os.pathsep + os.environ.get("PATH", "")
if os.name == "nt":
    site_packages = Path(os.sys.prefix) / "Lib" / "site-packages"
    candidates: list[Path] = [site_packages]
    torch_lib = site_packages / "torch" / "lib"
    if torch_lib.is_dir():
        os.environ["PATH"] = str(torch_lib) + os.pathsep + os.environ["PATH"]
        try:
            os.add_dll_directory(str(torch_lib))
        except OSError:
            pass
    nvidia_dir = site_packages / "nvidia"
    if nvidia_dir.is_dir():
        for pkg in nvidia_dir.iterdir():
            bin_dir = pkg / "bin"
            if bin_dir.is_dir():
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]
                try:
                    os.add_dll_directory(str(bin_dir))
                except OSError:
                    pass

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

import onnxruntime as ort
import modules.globals as dlc_globals
import modules.core as dlc_core


WEB_DIR = PROJECT_ROOT / "web"
OUTPUT_DIR = PROJECT_ROOT / "output"
TEMP_DIR = PROJECT_ROOT / "temp"
UPLOAD_DIR = TEMP_DIR / "uploads"
for directory in (OUTPUT_DIR, TEMP_DIR, UPLOAD_DIR):
    directory.mkdir(parents=True, exist_ok=True)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

app = FastAPI(title="Local Face Swapper", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

jobs: dict[str, dict[str, Any]] = {}
lock = threading.Lock()


def _status(job_id: str, message: str) -> None:
    with lock:
        job = jobs.get(job_id)
        if job:
            job["status"] = message
            job["updated"] = time.time()


def _patch_status(job_id: str) -> None:
    """Route Deep-Live-Cam's console status messages to the browser job."""
    def callback(message: str, scope: str = "DLC.CORE") -> None:
        _status(job_id, message)
        print(f"[{scope}] {message}", flush=True)

    dlc_core.update_status = callback
    # face_swapper imports update_status directly, so patch its module-local
    # reference after it is loaded by get_frame_processors_modules().
    try:
        processors = dlc_core.get_frame_processors_modules(["face_swapper"])
        for processor in processors:
            if hasattr(processor, "update_status"):
                processor.update_status = callback
    except Exception:
        pass


def _configure_dlc(source: Path, target: Path, output: Path) -> None:
    providers = ort.get_available_providers()
    if "CUDAExecutionProvider" not in providers:
        raise RuntimeError(
            "CUDAExecutionProvider is not available. The local setup requires "
            "onnxruntime-gpu 1.26.0 for the current Deep-Live-Cam repository."
        )

    dlc_globals.source_path = str(source)
    dlc_globals.target_path = str(target)
    dlc_globals.output_path = str(output)
    dlc_globals.frame_processors = ["face_swapper"]
    dlc_globals.headless = True
    dlc_globals.keep_fps = True
    dlc_globals.keep_audio = True
    dlc_globals.keep_frames = False
    dlc_globals.many_faces = False
    dlc_globals.map_faces = False
    dlc_globals.mouth_mask = False
    dlc_globals.nsfw_filter = False
    dlc_globals.video_encoder = "libx264"  # Deep-Live-Cam switches to NVENC with CUDA.
    dlc_globals.video_quality = 18
    dlc_globals.max_memory = 8
    dlc_globals.execution_providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    dlc_globals.execution_threads = 2
    dlc_globals.opacity = 1.0
    dlc_globals.sharpness = 0.0
    dlc_globals.enable_interpolation = False
    dlc_globals.interpolation_weight = 0.0
    for key in ("face_enhancer", "face_enhancer_gpen256", "face_enhancer_gpen512"):
        dlc_globals.fp_ui[key] = False


def _run_job(job_id: str, source: Path, target: Path, output: Path) -> None:
    try:
        _patch_status(job_id)
        _configure_dlc(source, target, output)
        _status(job_id, "Loading Deep-Live-Cam models…")
        dlc_core.limit_resources()
        dlc_core.start()
        if output.exists() and output.stat().st_size > 0:
            with lock:
                jobs[job_id]["state"] = "completed"
                jobs[job_id]["status"] = "Face swap completed."
                jobs[job_id]["output"] = output.name
                jobs[job_id]["updated"] = time.time()
        else:
            raise RuntimeError("Deep-Live-Cam did not create an output file.")
    except Exception as exc:
        print(f"[WEB] Job {job_id} failed: {exc}", flush=True)
        with lock:
            jobs[job_id]["state"] = "error"
            jobs[job_id]["status"] = str(exc)
            jobs[job_id]["updated"] = time.time()
    finally:
        try:
            dlc_core.release_resources()
        except Exception:
            pass


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})


@app.get("/api/providers")
def providers():
    available = ort.get_available_providers()
    return {"providers": available, "cuda": "CUDAExecutionProvider" in available}


@app.post("/api/swap")
async def swap(
    source: UploadFile = File(...),
    target: UploadFile = File(...),
    target_type: str = "image",
):
    source_ext = Path(source.filename or "").suffix.lower()
    target_ext = Path(target.filename or "").suffix.lower()
    if source_ext not in IMAGE_EXTS:
        raise HTTPException(400, "Source must be a JPG, JPEG, PNG, BMP, or WEBP image.")
    expected = IMAGE_EXTS if target_type == "image" else VIDEO_EXTS
    if target_ext not in expected:
        raise HTTPException(400, "Target file type does not match the selected target type.")
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        raise HTTPException(500, "CUDAExecutionProvider is not available in this environment.")

    job_id = uuid.uuid4().hex
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    source_path = job_dir / f"source{source_ext}"
    target_path = job_dir / f"target{target_ext}"
    output_ext = target_ext if target_type == "image" else ".mp4"
    output_path = OUTPUT_DIR / f"face-swap-{job_id}{output_ext}"

    with source_path.open("wb") as handle:
        shutil.copyfileobj(source.file, handle)
    with target_path.open("wb") as handle:
        shutil.copyfileobj(target.file, handle)

    with lock:
        jobs[job_id] = {
            "state": "processing",
            "status": "Queued…",
            "target_type": target_type,
            "output": None,
            "updated": time.time(),
        }

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, source_path, target_path, output_path),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    with lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    result = dict(job)
    if result.get("output"):
        result["url"] = f"/api/jobs/{job_id}/result"
    return result


@app.get("/api/jobs/{job_id}/result")
def job_result(job_id: str):
    with lock:
        job = jobs.get(job_id)
    if not job or job.get("state") != "completed":
        raise HTTPException(404, "Result is not ready.")
    filename = job.get("output")
    if not filename:
        raise HTTPException(404, "Output file not found.")
    output = OUTPUT_DIR / filename
    if not output.is_file():
        raise HTTPException(404, "Output file not found.")
    media = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".bmp": "image/bmp"}.get(output.suffix.lower(), "image/png")
    if output.suffix.lower() in VIDEO_EXTS or output.suffix.lower() == ".mp4":
        media = "video/mp4"
    return FileResponse(output, media_type=media, filename=output.name)