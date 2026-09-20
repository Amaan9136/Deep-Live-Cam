"""Real-time webcam face-swap session.

Reuses the existing Deep-Live-Cam engine (face analyser, face swapper,
model loading, CUDA/ONNX configuration) instead of a second engine. The
capture-thread + bounded-queue + cached-target-detection pattern mirrors
what benchmark_pipeline.py verified: detection runs every DETECT_EVERY
frames, the cached target face is reused in between, and frames are
dropped rather than queued when processing falls behind.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Any, Optional

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
        self._frame_ready = threading.Event()
        self._running = False
        self._camera_index: Optional[int] = None
        self._error: Optional[str] = None
        self._cached_face: Any = None
        self._frame_counter = 0
        self._fps_times: list[float] = []
        self._fps = 0.0

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

    def start(self, camera_index: int) -> None:
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
            dlc_globals.many_faces = False
            dlc_globals.map_faces = False
            dlc_globals.mouth_mask = False
            dlc_globals.poisson_blend = False
            dlc_globals.sharpness = 0.0
            dlc_globals.enable_interpolation = False
            dlc_globals.opacity = 1.0

            capturer = VideoCapturer(camera_index)
            if not capturer.start(width=CAPTURE_WIDTH, height=CAPTURE_HEIGHT, fps=CAPTURE_FPS):
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
            self._latest_jpeg = None
            self._frame_ready.clear()
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
        self._drain_queue()
        self._cached_face = None
        self._latest_jpeg = None
        self._frame_ready.clear()

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
        }

    def latest_jpeg(self, timeout: float = 1.0) -> Optional[bytes]:
        if self._frame_ready.wait(timeout):
            return self._latest_jpeg
        return None

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

            self._frame_counter += 1
            if self._cached_face is None or self._frame_counter % DETECT_EVERY == 0:
                try:
                    self._cached_face = detect_one_face_fast(frame)
                except Exception:
                    self._cached_face = None

            try:
                processed = (
                    process_frame(self._source_face, frame, target_face=self._cached_face)
                    if self._cached_face is not None
                    else frame
                )
            except Exception as exc:
                self._error = str(exc)
                processed = frame

            if STREAM_MAX_WIDTH and processed.shape[1] > STREAM_MAX_WIDTH:
                scale = STREAM_MAX_WIDTH / processed.shape[1]
                processed = cv2.resize(
                    processed,
                    (STREAM_MAX_WIDTH, int(processed.shape[0] * scale)),
                    interpolation=cv2.INTER_AREA,
                )

            ok, encoded = cv2.imencode(".jpg", processed, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if ok:
                self._latest_jpeg = encoded.tobytes()
                self._frame_ready.set()

            now = time.time()
            self._fps_times.append(now)
            self._fps_times = [t for t in self._fps_times if now - t <= 2.0]
            if len(self._fps_times) >= 2:
                self._fps = (len(self._fps_times) - 1) / (self._fps_times[-1] - self._fps_times[0])


SESSION = RealtimeCameraSession()
