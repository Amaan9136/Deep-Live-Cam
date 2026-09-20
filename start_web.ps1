$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

# First launch bootstraps the current official repository into this directory.
if (-not (Test-Path (Join-Path $ProjectRoot "modules"))) {
    Write-Host "Deep-Live-Cam source is missing. Cloning the current official repository..." -ForegroundColor Cyan
    $stage = Join-Path $env:TEMP ("Deep-Live-Cam-" + [guid]::NewGuid().ToString("N"))
    git clone --depth 1 https://github.com/hacksider/Deep-Live-Cam.git $stage
    Get-ChildItem -Force $stage | ForEach-Object {
        Move-Item -Force $_.FullName $ProjectRoot
    }
    Remove-Item -Recurse -Force $stage
}

$python = "C:\Users\Amaan M k\.conda\envs\trainer\python.exe"
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

& $python -m pip install -r requirements.txt

# requirements.txt already pins onnxruntime-gpu==1.26.0 for this platform,
# so a separate reinstall step is unnecessary.

# Ensure the web runtime uses the same project root as the repository.
$env:PYTHONPATH = $ProjectRoot
Write-Host "Starting LOCAL FACE SWAPPER at http://127.0.0.1:8000" -ForegroundColor Green
& $python -m uvicorn web.app:app --host 127.0.0.1 --port 8000