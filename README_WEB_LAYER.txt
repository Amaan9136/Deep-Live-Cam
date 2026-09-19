This package adds a thin FastAPI browser layer to the current official Deep-Live-Cam repository.

Place/extract this package as the Deep-Live-Cam project directory, then run start_web.ps1.
If the repository is not present yet, start_web.ps1 clones the current official repository first.
The web layer reuses Deep-Live-Cam's existing face analyser, face swapper, in-memory FFmpeg
video pipeline, NVENC selection, audio restoration, model loading, and CUDA execution provider.
