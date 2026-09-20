"""Real-time webcam face-swap session.
Reuses the existing Deep-Live-Cam engine (face analyser, face swapper,
model loading, CUDA/ONNX configuration) instead of a second engine. The
capture-thread + bounded-queue + cached-target-detection pattern mirrors
what benchmark_pipeline.py verified: detection runs every DETECT_EVERY
frames, the cached target face is reused in between, and frames are
dropped rather than queued when processing falls behind.
"""
from __future__ import annotations
import importlib
import queue
import threading
import time
from typing import Any, Optional, Tuple
import cv2
import modules.globals as dlc_globals
from modules import imread_unicode
from modules.face_analyser import get_face_analyser, get_one_face, detect_one_face_fast
from modules.model_downloader import is_present as _model_present
from modules.processors.frame.face_swapper import get_face_swapper, process_frame
from modules.video_capture import VideoCapturer, list_cameras
DETECT_EVERY = 3
CAPTURE_WIDTH = 1920
CAPTURE_HEIGHT = 1080
CAPTURE_FPS = 30
STREAM_MAX_WIDTH = 960
JPEG_QUALITY = 80
MAX_READ_FAILURES = 60
ENHANCER_MODULES = {"gfpgan": "face_enhancer", "gpen256": "face_enhancer_gpen256", "gpen512": "face_enhancer_gpen512"}
DEFAULT_OPTIONS = {
    "many_faces": False,
    "enhancer": "none",
    "opacity": 1.0,
    "sharpness": 0.0,
    "mouth_mask_size": 0,
    "poisson_blend": False,
    "interpolation": False,
    "interpolation_weight": 0.5,
    "mirror": False,
    "detect_every": DETECT_EVERY,
    "stream_width": STREAM_MAX_WIDTH,
    "jpeg_quality": JPEG_QUALITY,
    "capture_width": CAPTURE_WIDTH,
    "capture_height": CAPTURE_HEIGHT,
    "capture_fps": CAPTURE_FPS,
    "virtual_cam": False,
}
class RealtimeCameraSession:
    """Owns the capture thread, worker thread, and shared state for the
    one real-time face-swap session this app supports at a time. A single
    instance is reused across start/stop cycles."""
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._source_path: Optional[str] = None
        self._source_face: Any = None
        self._capturer: Optional[VideoCapturer] = None
        self._capture_thread: Optional[threading.Thread] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._frame_queue: "queue.Queue" = queue.Queue(maxsize=1)
        self._latest_jpeg: Optional[bytes] = None
        self._frame_cond = threading.Condition()
        self._frame_version = 0
        self._running = False
        self._camera_index: Optional[int] = None
        self._error: Optional[str] = None
        self._cached_face: Any = None
        self._frame_counter = 0
        self._fps_times: list[float] = []
        self._fps = 0.0
        self._options: dict[str, Any] = dict(DEFAULT_OPTIONS)
        self._mirrored = False
        self._vcam: Any = None
        self._vcam_failed = False
    def set_source(self, path: str) -> None:
        """Read and analyse the source image once, caching it by path."""
        with self._lock:
            if self._source_path == path and self._source_face is not None:
                return
            frame = imread_unicode(path)
            if frame is None:
                self._source_path = None
                self._source_face = None
                raise RuntimeError("The source image could not be read.")
            face = get_one_face(frame)
            if face is None:
                self._source_path = None
                self._source_face = None
                raise RuntimeError("No face detected in the source image.")
            self._source_path = path
            self._source_face = face
    @staticmethod
    def cameras() -> list:
        return list_cameras()
    @staticmethod
    def _enhancer(name: str) -> Any:
        return importlib.import_module(f"modules.processors.frame.{ENHANCER_MODULES[name]}")
    def _ensure_vcam(self) -> Any:
        if self._vcam_failed:
            return None
        if self._vcam is not None:
            return self._vcam
        try:
            import pyvirtualcam
            capturer = self._capturer
            fps = round(capturer.actual_fps) if capturer and capturer.actual_fps else self._options["capture_fps"]
            self._vcam = pyvirtualcam.Camera(
                width=capturer.actual_width,
                height=capturer.actual_height,
                fps=max(1, fps),
                print_fps=False,
            )
        except Exception as exc:
            self._vcam_failed = True
            self._error = f"Virtual camera unavailable: {exc}"
            return None
        return self._vcam
    def _close_vcam(self) -> None:
        if self._vcam is not None:
            try:
                self._vcam.close()
            except Exception:
                pass
            self._vcam = None
        self._vcam_failed = False
    def configure(self, options: dict) -> None:
        merged = {**DEFAULT_OPTIONS, **options}
        if merged["enhancer"] != "none":
            try:
                module = self._enhancer(merged["enhancer"])
                (getattr(module, "get_enhancer", None) or module.get_face_enhancer)()
            except Exception as exc:
                raise RuntimeError(f"Face enhancer failed to load: {exc}")
        self._options = merged
        dlc_globals.many_faces = merged["many_faces"]
        dlc_globals.poisson_blend = merged["poisson_blend"]
        dlc_globals.sharpness = merged["sharpness"]
        dlc_globals.opacity = merged["opacity"]
        dlc_globals.mouth_mask = merged["mouth_mask_size"] > 0
        dlc_globals.mouth_mask_size = float(merged["mouth_mask_size"])
        dlc_globals.enable_interpolation = merged["interpolation"]
        dlc_globals.interpolation_weight = merged["interpolation_weight"] if merged["interpolation"] else 0.0
    def start(self, camera_index: int, options: Optional[dict] = None) -> None:
        with self._lock:
            if self._running:
                return
            if self._source_face is None:
                raise RuntimeError("Select a source face before starting the camera.")
            import onnxruntime as ort
            if "CUDAExecutionProvider" not in ort.get_available_providers():
                raise RuntimeError("CUDAExecutionProvider is not available in this environment.")
            if not (_model_present("inswapper_128_fp16.onnx") or _model_present("inswapper_128.onnx")):
                raise RuntimeError("No face swapper model found. Download it from the Models panel first.")
            if "CUDAExecutionProvider" not in dlc_globals.execution_providers:
                dlc_globals.execution_providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            dlc_globals.frame_processors = ["face_swapper"]
            dlc_globals.map_faces = False
            self.configure(options or {})
            capturer = VideoCapturer(camera_index)
            if not capturer.start(width=self._options["capture_width"], height=self._options["capture_height"], fps=self._options["capture_fps"]):
                raise RuntimeError(f"Could not open camera {camera_index}.")
            get_face_analyser()
            if get_face_swapper() is None:
                capturer.release()
                raise RuntimeError("Face swapper model failed to load.")
            self._capturer = capturer
            self._camera_index = camera_index
            self._cached_face = None
            self._frame_counter = 0
            self._fps_times = []
            self._fps = 0.0
            self._error = None
            self._stop_event.clear()
            self._drain_queue()
            with self._frame_cond:
                self._latest_jpeg = None
                self._frame_version = 0
            self._running = True
            self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._capture_thread.start()
            self._worker_thread.start()
    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
        self._stop_event.set()
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=2.0)
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=2.0)
        if self._capturer is not None:
            self._capturer.release()
        self._capturer = None
        self._capture_thread = None
        self._worker_thread = None
        self._close_vcam()
        self._drain_queue()
        self._cached_face = None
        with self._frame_cond:
            self._latest_jpeg = None
            self._frame_version += 1
            self._frame_cond.notify_all()
    def status(self) -> dict:
        camera = None
        if self._capturer is not None:
            camera = {
                "index": self._camera_index,
                "width": self._capturer.actual_width,
                "height": self._capturer.actual_height,
                "fps": round(self._capturer.actual_fps, 1),
            }
        return {
            "running": self._running,
            "source_ready": self._source_face is not None,
            "camera": camera,
            "fps": round(self._fps, 1),
            "error": self._error,
            "virtual_cam": {
                "active": self._vcam is not None,
                "device": getattr(self._vcam, "device", None),
            },
        }
    def latest_jpeg(self, after_version: int = 0, timeout: float = 1.0) -> Tuple[Optional[bytes], int]:
        with self._frame_cond:
            if self._frame_version == after_version:
                self._frame_cond.wait(timeout)
            return self._latest_jpeg, self._frame_version
    def _drain_queue(self) -> None:
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break
    def _capture_loop(self) -> None:
        capturer = self._capturer
        failures = 0
        while not self._stop_event.is_set():
            ok, frame = capturer.read()
            if not ok or frame is None:
                failures += 1
                if failures > MAX_READ_FAILURES:
                    self._error = "Camera disconnected."
                    self._stop_event.set()
                    with self._frame_cond:
                        self._frame_cond.notify_all()
                    break
                time.sleep(0.01)
                continue
            failures = 0
            try:
                self._frame_queue.put_nowait(frame)
            except queue.Full:
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._frame_queue.put_nowait(frame)
                except queue.Full:
                    pass
    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                frame = self._frame_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            options = self._options
            many = options["many_faces"]
            if options["mirror"] != self._mirrored:
                self._mirrored = options["mirror"]
                self._cached_face = None
            if self._mirrored:
                frame = cv2.flip(frame, 1)
            self._frame_counter += 1
            if not many and (self._cached_face is None or self._frame_counter % options["detect_every"] == 0):
                try:
                    self._cached_face = detect_one_face_fast(frame)
                except Exception:
                    self._cached_face = None
            try:
                processed = (
                    process_frame(self._source_face, frame, target_face=self._cached_face)
                    if many or self._cached_face is not None
                    else frame
                )
            except Exception as exc:
                self._error = str(exc)
                processed = frame
            if options["enhancer"] != "none" and (many or self._cached_face is not None):
                try:
                    processed = self._enhancer(options["enhancer"]).process_frame(
                        None, processed, detected_faces=None if many else [self._cached_face]
                    )
                except Exception as exc:
                    self._error = str(exc)
            if options["virtual_cam"]:
                vcam = self._ensure_vcam()
                if vcam is not None:
                    try:
                        vcam.send(cv2.cvtColor(processed, cv2.COLOR_BGR2RGB))
                        vcam.sleep_until_next_frame()
                    except Exception as exc:
                        self._error = str(exc)
            else:
                self._close_vcam()
            if options["stream_width"] and processed.shape[1] > options["stream_width"]:
                scale = options["stream_width"] / processed.shape[1]
                processed = cv2.resize(
                    processed,
                    (options["stream_width"], int(processed.shape[0] * scale)),
                    interpolation=cv2.INTER_AREA,
                )
            ok, encoded = cv2.imencode(".jpg", processed, [cv2.IMWRITE_JPEG_QUALITY, options["jpeg_quality"]])
            if ok:
                with self._frame_cond:
                    self._latest_jpeg = encoded.tobytes()
                    self._frame_version += 1
                    self._frame_cond.notify_all()
            now = time.time()
            self._fps_times.append(now)
            self._fps_times = [t for t in self._fps_times if now - t <= 2.0]
            if len(self._fps_times) >= 2:
                self._fps = (len(self._fps_times) - 1) / (self._fps_times[-1] - self._fps_times[0])
SESSION = RealtimeCameraSession()