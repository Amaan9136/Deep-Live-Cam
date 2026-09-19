from __future__ import annotations
import os
import re
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
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request
from tqdm import tqdm
import onnxruntime as ort
import modules.globals as dlc_globals
import modules.core as dlc_core
import modules.model_downloader as dlc_models
import modules.processors.frame.core as dlc_frame_core
WEB_DIR = PROJECT_ROOT / "web"
OUTPUT_DIR = PROJECT_ROOT / "output"
TEMP_DIR = PROJECT_ROOT / "temp"
UPLOAD_DIR = TEMP_DIR / "uploads"
MODELS_DIR = Path(dlc_models.MODELS_DIR)
INSIGHTFACE_DIR = Path.home() / ".insightface" / "models" / "buffalo_l"
for directory in (OUTPUT_DIR, TEMP_DIR, UPLOAD_DIR, MODELS_DIR):
    directory.mkdir(parents=True, exist_ok=True)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".bmp": "image/bmp", ".mp4": "video/mp4"}
SWAPPER_FILES = ["inswapper_128_fp16.onnx", "inswapper_128.onnx"]
ENHANCERS = {"gfpgan": "face_enhancer", "gpen256": "face_enhancer_gpen256", "gpen512": "face_enhancer_gpen512"}
ENHANCER_FILES = {"gfpgan": "gfpgan-1024.onnx", "gpen256": "GPEN-BFR-256.onnx", "gpen512": "GPEN-BFR-512.onnx"}
ERROR_PATTERN = re.compile(r"error|not found|could not|failed|no face|no inswapper", re.I)
MODEL_CATALOG: list[dict[str, Any]] = [
    {"name": "inswapper_128_fp16.onnx", "label": "Face swapper (FP16)", "group": "swapper", "note": "Recommended for RTX GPUs. Half the size of FP32."},
    {"name": "inswapper_128.onnx", "label": "Face swapper (FP32)", "group": "swapper", "note": "Alternative to FP16. Only one swapper is needed."},
    {"name": "gfpgan-1024.onnx", "label": "GFPGAN enhancer", "group": "enhancer", "note": "Best detail, heaviest on VRAM."},
    {"name": "GPEN-BFR-256.onnx", "label": "GPEN-256 enhancer", "group": "enhancer", "note": "Lightest enhancer. Good for 4 GB VRAM."},
    {"name": "GPEN-BFR-512.onnx", "label": "GPEN-512 enhancer", "group": "enhancer", "note": "Balanced quality and speed."},
] + [
    {"name": name, "label": name.rsplit("/", 1)[-1], "group": "analyser", "dir": str(INSIGHTFACE_DIR), "note": "Face detection pack (buffalo_l). Saved to the insightface folder."}
    for name in dlc_models.MODEL_SIZES
    if name.startswith("buffalo_l/")
]
CATALOG = {entry["name"]: entry for entry in MODEL_CATALOG}
app = FastAPI(title="Local Face Swapper", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
jobs: dict[str, dict[str, Any]] = {}
downloads: dict[str, dict[str, Any]] = {}
lock = threading.Lock()
run_lock = threading.Lock()
class DownloadRequest(BaseModel):
    names: list[str]
class _JobProgress(tqdm):
    job_id: str | None = None
    def update(self, n=1):
        shown = super().update(n)
        _progress(_JobProgress.job_id, self.n, self.total)
        return shown
def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
def _present(entry: dict[str, Any]) -> bool:
    return dlc_models.is_present(entry["name"], entry.get("dir"))
def _model_path(entry: dict[str, Any]) -> str:
    return dlc_models.local_path(entry["name"], entry.get("dir"))
def _manual_hint(entry: dict[str, Any]) -> str:
    return f"Download {dlc_models.resolve_url(entry['name'])} and save it as {_model_path(entry)}."
def _status(job_id: str, message: str) -> None:
    with lock:
        job = jobs.get(job_id)
        if job:
            job["status"] = message
            job["updated"] = time.time()
            if not job["log"] or job["log"][-1]["message"] != message:
                job["log"] = (job["log"] + [{"time": time.time(), "message": message}])[-40:]
def _progress(job_id: str | None, done: float, total: float | None, unit: str = "frames") -> None:
    with lock:
        job = jobs.get(job_id) if job_id else None
        if job and total:
            job["progress"] = {"done": int(done), "total": int(total), "unit": unit}
            job["updated"] = time.time()
def _patch_status(job_id: str) -> None:
    """Route Deep-Live-Cam's console status messages to the browser job."""
    def callback(message: str, scope: str = "DLC.CORE") -> None:
        _status(job_id, message)
        if ERROR_PATTERN.search(message):
            with lock:
                jobs[job_id]["errors"].append(message)
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
    _JobProgress.job_id = job_id
    dlc_frame_core.tqdm = _JobProgress
def _configure_dlc(source: Path, target: Path, output: Path, options: dict[str, Any]) -> None:
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
    dlc_globals.keep_fps = options["keep_fps"]
    dlc_globals.keep_audio = options["keep_audio"]
    dlc_globals.keep_frames = False
    dlc_globals.many_faces = options["many_faces"]
    dlc_globals.map_faces = False
    dlc_globals.mouth_mask = options["mouth_mask_size"] > 0
    dlc_globals.mouth_mask_size = float(options["mouth_mask_size"])
    dlc_globals.poisson_blend = options["poisson_blend"]
    dlc_globals.nsfw_filter = False
    dlc_globals.video_encoder = "libx264"  # Deep-Live-Cam switches to NVENC with CUDA.
    dlc_globals.video_quality = options["video_quality"]
    dlc_globals.max_memory = 8
    dlc_globals.execution_providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    dlc_globals.execution_threads = options["threads"]
    dlc_globals.opacity = options["opacity"]
    dlc_globals.sharpness = options["sharpness"]
    dlc_globals.enable_interpolation = options["interpolation"]
    dlc_globals.interpolation_weight = options["interpolation_weight"] if options["interpolation"] else 0.0
    for key in ("face_enhancer", "face_enhancer_gpen256", "face_enhancer_gpen512"):
        dlc_globals.fp_ui[key] = ENHANCERS.get(options["enhancer"]) == key
def _torch_cuda() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False
def _fetch(entry: dict[str, Any], job_id: str | None = None) -> bool:
    name = entry["name"]
    dest = entry.get("dir")
    part = dlc_models.local_path(name, dest) + ".part"
    total = dlc_models.expected_size(name) or 0
    with lock:
        downloads[name] = {"state": "downloading", "done": 0, "total": total, "error": None}
    outcome: dict[str, Any] = {}
    worker = threading.Thread(
        target=lambda: outcome.update(path=dlc_models.ensure_model(name, quiet=True, dest_dir=dest)),
        daemon=True,
    )
    worker.start()
    while worker.is_alive():
        done = os.path.getsize(part) if os.path.isfile(part) else 0
        with lock:
            downloads[name]["done"] = done
        if job_id:
            _progress(job_id, done, total, "bytes")
            _status(job_id, f"Downloading {entry['label']}… {int(done * 100 / total) if total else 0}%")
        worker.join(0.5)
    ok = outcome.get("path") is not None
    with lock:
        downloads[name].update(
            state="done" if ok else "error",
            done=total if ok else downloads[name]["done"],
            error=None if ok else "Download failed. " + _manual_hint(entry),
        )
    return ok
def _download_many(entries: list[dict[str, Any]]) -> None:
    for entry in entries:
        _fetch(entry)
def _prepare_models(job_id: str, options: dict[str, Any]) -> None:
    swappers = [CATALOG[name] for name in SWAPPER_FILES]
    if not _torch_cuda():
        swappers.reverse()
    if not any(_present(entry) for entry in swappers):
        for entry in swappers:
            if _fetch(entry, job_id):
                break
        else:
            raise RuntimeError("Could not download the face swapper model. " + _manual_hint(swappers[0]))
    wanted = [CATALOG[ENHANCER_FILES[options["enhancer"]]]] if options["enhancer"] in ENHANCER_FILES else []
    wanted += [entry for entry in MODEL_CATALOG if entry["group"] == "analyser"]
    for entry in wanted:
        if not _present(entry) and not _fetch(entry, job_id):
            raise RuntimeError(f"Could not download {entry['label']}. " + _manual_hint(entry))
    with lock:
        jobs[job_id]["progress"] = None
def _preflight(job_id: str, source: Path, target: Path) -> None:
    from modules import imread_unicode
    from modules.face_analyser import get_many_faces
    _status(job_id, "Detecting faces…")
    source_frame = imread_unicode(str(source))
    if source_frame is None or not get_many_faces(source_frame):
        raise RuntimeError("No face detected in the source image. Use a clear, front-facing photo.")
    if target.suffix.lower() in IMAGE_EXTS:
        target_frame = imread_unicode(str(target))
        if target_frame is None:
            raise RuntimeError("The target image could not be read.")
        faces = get_many_faces(target_frame)
        if not faces:
            raise RuntimeError("No face detected in the target image.")
        _status(job_id, f"Found {len(faces)} face(s) in the target image.")
def _run_job(job_id: str, source: Path, target: Path, output: Path, options: dict[str, Any]) -> None:
    _status(job_id, "Waiting for the current job to finish…")
    with run_lock:
        with lock:
            jobs[job_id]["started"] = time.time()
        try:
            _prepare_models(job_id, options)
            _configure_dlc(source, target, output, options)
            _patch_status(job_id)
            _status(job_id, "Loading Deep-Live-Cam models…")
            dlc_core.limit_resources()
            _preflight(job_id, source, target)
            dlc_core.start()
            errors = jobs[job_id]["errors"]
            if target.suffix.lower() in IMAGE_EXTS and errors:
                output.unlink(missing_ok=True)
                raise RuntimeError(errors[-1])
            if output.exists() and output.stat().st_size > 0:
                with lock:
                    jobs[job_id]["state"] = "completed"
                    jobs[job_id]["status"] = "Face swap completed."
                    jobs[job_id]["output"] = output.name
                    jobs[job_id]["size"] = output.stat().st_size
                    jobs[job_id]["finished"] = jobs[job_id]["updated"] = time.time()
            else:
                raise RuntimeError(errors[-1] if errors else "Deep-Live-Cam did not create an output file.")
        except Exception as exc:
            print(f"[WEB] Job {job_id} failed: {exc}", flush=True)
            with lock:
                jobs[job_id]["state"] = "error"
                jobs[job_id]["status"] = str(exc)
                jobs[job_id]["finished"] = jobs[job_id]["updated"] = time.time()
        finally:
            try:
                dlc_core.release_resources()
            except Exception:
                pass
def _output_file(name: str) -> Path:
    path = OUTPUT_DIR / name
    if Path(name).name != name or not path.is_file():
        raise HTTPException(404, "Output file not found.")
    return path
def _serve(path: Path, download: bool):
    return FileResponse(
        path,
        media_type=MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"),
        filename=path.name if download else None,
        content_disposition_type="attachment" if download else "inline",
    )
@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})
@app.get("/api/providers")
def providers():
    available = ort.get_available_providers()
    return {"providers": available, "cuda": "CUDAExecutionProvider" in available}
@app.get("/api/system")
def system():
    available = ort.get_available_providers()
    gpu = None
    try:
        import torch
        if torch.cuda.is_available():
            gpu = torch.cuda.get_device_name(0)
    except Exception:
        pass
    return {
        "providers": available,
        "cuda": "CUDAExecutionProvider" in available,
        "gpu": gpu,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "models_dir": str(MODELS_DIR),
        "output_dir": str(OUTPUT_DIR),
        "busy": run_lock.locked(),
    }
@app.get("/api/models")
def models():
    items = []
    with lock:
        states = {name: dict(state) for name, state in downloads.items()}
    for entry in MODEL_CATALOG:
        present = _present(entry)
        state = states.get(entry["name"]) or {}
        items.append({
            "name": entry["name"],
            "label": entry["label"],
            "group": entry["group"],
            "note": entry["note"],
            "size": dlc_models.expected_size(entry["name"]),
            "present": present,
            "path": _model_path(entry),
            "url": dlc_models.resolve_url(entry["name"]),
            "state": "ready" if present else state.get("state", "missing"),
            "done": state.get("done", 0),
            "error": None if present else state.get("error"),
        })
    swapper_ready = any(item["present"] for item in items if item["group"] == "swapper")
    analyser_ready = all(item["present"] for item in items if item["group"] == "analyser")
    return {
        "directory": str(MODELS_DIR),
        "analyser_directory": str(INSIGHTFACE_DIR),
        "models": items,
        "ready": swapper_ready and analyser_ready,
        "swapper_ready": swapper_ready,
        "analyser_ready": analyser_ready,
    }
@app.delete("/api/models/{name:path}")
def model_delete(name: str):
    if name not in CATALOG:
        raise HTTPException(404, f"Unknown model: {name}")
    entry = CATALOG[name]
    path = Path(_model_path(entry))
    path.unlink(missing_ok=True)
    Path(str(path) + ".part").unlink(missing_ok=True)
    with lock:
        downloads.pop(name, None)
    return {"deleted": name}
@app.post("/api/models/download")
def models_download(request: DownloadRequest):
    entries = []
    for name in request.names:
        if name not in CATALOG:
            raise HTTPException(400, f"Unknown model: {name}")
        entries.append(CATALOG[name])
    with lock:
        pending = [
            entry for entry in entries
            if not _present(entry) and downloads.get(entry["name"], {}).get("state") not in ("queued", "downloading")
        ]
        for entry in pending:
            downloads[entry["name"]] = {"state": "queued", "done": 0, "total": dlc_models.expected_size(entry["name"]) or 0, "error": None}
    if pending:
        threading.Thread(target=_download_many, args=(pending,), daemon=True).start()
    return {"queued": [entry["name"] for entry in pending]}
@app.post("/api/swap")
async def swap(
    source: UploadFile = File(...),
    target: UploadFile = File(...),
    target_type: str = Form("image"),
    many_faces: bool = Form(False),
    enhancer: str = Form("none"),
    opacity: float = Form(100),
    sharpness: float = Form(0),
    mouth_mask_size: int = Form(0),
    poisson_blend: bool = Form(False),
    interpolation: bool = Form(False),
    interpolation_weight: float = Form(0.5),
    keep_fps: bool = Form(True),
    keep_audio: bool = Form(True),
    video_quality: int = Form(18),
    threads: int = Form(2),
):
    source_ext = Path(source.filename or "").suffix.lower()
    target_ext = Path(target.filename or "").suffix.lower()
    if source_ext not in IMAGE_EXTS:
        raise HTTPException(400, "Source must be a JPG, JPEG, PNG, BMP, or WEBP image.")
    expected = IMAGE_EXTS if target_type == "image" else VIDEO_EXTS
    if target_ext not in expected:
        raise HTTPException(400, "Target file type does not match the selected target type.")
    if enhancer != "none" and enhancer not in ENHANCERS:
        raise HTTPException(400, "Unknown face enhancer.")
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        raise HTTPException(500, "CUDAExecutionProvider is not available in this environment.")
    if target_type == "video" and not shutil.which("ffmpeg"):
        raise HTTPException(500, "FFmpeg was not found on PATH. Install FFmpeg to process videos.")
    options = {
        "many_faces": many_faces,
        "enhancer": enhancer,
        "opacity": _clamp(opacity, 0, 100) / 100,
        "sharpness": _clamp(sharpness, 0, 5),
        "mouth_mask_size": int(_clamp(mouth_mask_size, 0, 100)),
        "poisson_blend": poisson_blend,
        "interpolation": interpolation and target_type == "video",
        "interpolation_weight": _clamp(interpolation_weight, 0.05, 0.95),
        "keep_fps": keep_fps,
        "keep_audio": keep_audio,
        "video_quality": int(_clamp(video_quality, 0, 51)),
        "threads": int(_clamp(threads, 1, 32)),
    }
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
            "progress": None,
            "log": [],
            "errors": [],
            "options": options,
            "created": time.time(),
            "started": None,
            "finished": None,
            "updated": time.time(),
        }
    thread = threading.Thread(
        target=_run_job,
        args=(job_id, source_path, target_path, output_path, options),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}
@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    with lock:
        job = jobs.get(job_id)
        result = dict(job) if job else None
        if result:
            result["log"] = list(job["log"])
    if not result:
        raise HTTPException(404, "Job not found.")
    result["now"] = time.time()
    if result.get("output"):
        result["url"] = f"/api/jobs/{job_id}/result"
    return result
@app.get("/api/jobs/{job_id}/result")
def job_result(job_id: str, download: bool = False):
    with lock:
        job = jobs.get(job_id)
    if not job or job.get("state") != "completed":
        raise HTTPException(404, "Result is not ready.")
    filename = job.get("output")
    if not filename:
        raise HTTPException(404, "Output file not found.")
    return _serve(_output_file(filename), download)
@app.get("/api/outputs")
def outputs():
    files = sorted(
        (p for p in OUTPUT_DIR.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS | VIDEO_EXTS),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:60]
    return {
        "items": [
            {
                "name": p.name,
                "kind": "video" if p.suffix.lower() in VIDEO_EXTS else "image",
                "size": p.stat().st_size,
                "modified": p.stat().st_mtime,
                "url": f"/api/outputs/{p.name}",
            }
            for p in files
        ]
    }
@app.get("/api/outputs/{name}")
def output_file(name: str, download: bool = False):
    return _serve(_output_file(name), download)
@app.delete("/api/outputs/{name}")
def output_delete(name: str):
    _output_file(name).unlink()
    return {"deleted": name}