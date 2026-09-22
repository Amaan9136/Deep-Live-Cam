# CLAUDE.md

Guidance for Claude Code (or any AI agent) working in this repository.

## What this project is

`faceswap-live` is a FastAPI web wrapper around
[Deep-Live-Cam](https://github.com/hacksider/Deep-Live-Cam). It does **not** reimplement
the face-swap engine — it reuses Deep-Live-Cam's face analyser, face swapper/enhancer
processors, and video pipeline as-is, and adds a browser UI, a JSON API, and real-time
webcam streaming on top.

- Entry point: `run_web.py` -> starts `uvicorn` serving `web.app:app` (default
  `127.0.0.1:8000`).
- `web/app.py` — the FastAPI app: routes for image/video swap jobs, the realtime webcam
  MJPEG stream, and the model manager.
- `web/templates/`, `web/static/` — server-rendered HTML/CSS/JS for the control panel.
- `modules/` — the Deep-Live-Cam engine code: `core.py` (job orchestration),
  `face_analyser.py`, `processors/` (face swapper/enhancer frame processors),
  `realtime_camera.py` (capture + worker thread pair for the live path),
  `gpu_processing.py` (execution-provider selection), `globals.py` (shared runtime
  state/config), `model_downloader.py`, `utilities.py`.

## Conventions to follow

- **Match existing style per file.** No formatter/linter is enforced; follow the
  naming, typing, and structure already used in the file you're editing.
- **Keep changes focused and minimal.** Touch only the lines a change requires; don't
  reformat, reorder, or add unrelated cleanup in the same diff.
- **No added comments or blank lines for their own sake** — this repo's existing files
  are lightly commented; don't pad new code with explanatory comments unless the
  surrounding code already does so for similarly non-obvious logic.
- **Engine vs. web layer.** Bug fixes or features that belong to the core face-swap
  engine (accuracy, model behavior, blending algorithms) conceptually belong upstream in
  Deep-Live-Cam; this repo's own scope is the web/API/streaming layer around it. Keep
  that distinction in mind when deciding where a change belongs.
- **Config lives in `modules/globals.py`.** Shared runtime state and options (paths,
  processing flags, live-mode settings, execution providers) are module-level globals
  there, not a class/config object — new options should follow that same pattern unless
  refactoring globals.py itself is the explicit task.
- **Unicode-safe file I/O.** Use `modules/__init__.py`'s `imread_unicode` /
  `imwrite_unicode` instead of raw `cv2.imread` / `cv2.imwrite` for any new code path
  that reads or writes image files, since plain OpenCV I/O silently fails on non-ASCII
  Windows paths.

## Dependencies

- Python deps are pinned/bounded in `requirements.txt`
- Dependency updates are managed by Dependabot (`.github/dependabot.yml`) — see that
  file for what it watches and why.
