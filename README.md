# Deep-Live-Cam Local Web Interface
This package adds a thin FastAPI browser layer to the official
Deep-Live-Cam repository.
## Purpose
Provides a completely local browser interface for:
- Image → Image face swapping
- Image → Video face swapping
- GPU-accelerated inference
- Local output files
- Browser image/video preview
- Downloading generated results
Everything runs locally on the Windows PC.
## Start
Use the existing `trainer` Conda environment:
    conda activate trainer
    & .\start_web.ps1
Then open:
    http://127.0.0.1:8000
## Repository
Official Deep-Live-Cam:
    https://github.com/hacksider/Deep-Live-Cam.git
If the Deep-Live-Cam repository is not present yet, `start_web.ps1`
clones the current official repository automatically.
## Web Layer
The added web application is located under:
    web/
        app.py
        templates/
            index.html
        static/
            app.js
            style.css
Additional files:
    start_web.ps1
    requirements-web.txt
    output/
    temp/
## Integration
The web layer is designed to reuse Deep-Live-Cam's existing functionality
rather than replacing the face-swapping engine.
It uses the existing:
- Face analyser
- Face swapper
- Model loading
- Face detection
- Video processing
- FFmpeg processing
- NVENC selection
- Audio restoration
- CUDA execution provider
## GPU
The intended GPU is the NVIDIA RTX 3050.
ONNX Runtime GPU is used for ONNX inference so Deep-Live-Cam can use
CUDAExecutionProvider.
The existing PyTorch installation is not intentionally replaced.
## Video Processing
Video frames are processed sequentially rather than loading an entire
video into GPU memory.
The implementation is intended to remain suitable for a GPU with
4 GB VRAM.
Where technically possible:
- Original FPS is preserved
- Original resolution is preserved
- Original audio is restored/preserved
- FFmpeg is used for video handling
## Supported Inputs
Source face:
- JPG
- JPEG
- PNG
Target image:
- JPG
- JPEG
- PNG
Target video:
- MP4
- MOV
- AVI
- MKV
Actual codec/container support depends on the installed FFmpeg/OpenCV
support.
## Output
Generated files are stored locally under:
    output/
Temporary processing files are stored under:
    temp/
No cloud service, database, account, login, Docker container, or
internet-facing server is required.
## Important
The Deep-Live-Cam repository remains the underlying face-swapping engine.
The added FastAPI application is only a local browser/API interface around
that implementation.