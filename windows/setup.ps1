# ──────────────────────────────────────────────────────────────
# setup.ps1 — Bootstrap the trojan-detector project (Windows PowerShell)
#
# Usage:
#   .\setup.ps1            Install core + GUI + training deps
#   .\setup.ps1 -Core      Install core deps only (no GUI, no training)
#   .\setup.ps1 -Dev       Install everything including dev/test tools
# ──────────────────────────────────────────────────────────────

param(
    [switch]$Core,
    [switch]$Dev
)

$ErrorActionPreference = "Stop"

# ── Configuration ──────────────────────────────────────────────
$PythonCmd = "python"
$VenvDir = ".venv"

# Determine extras to install
$Extras = "gui,training"
if ($Core) {
    $Extras = ""
}
elseif ($Dev) {
    $Extras = "all"
}

# ── Helper Functions ───────────────────────────────────────────
function Write-Info($msg) {
    Write-Host "[INFO]  " -ForegroundColor Green -NoNewline
    Write-Host $msg
}

function Write-Warn($msg) {
    Write-Host "[WARN]  " -ForegroundColor Yellow -NoNewline
    Write-Host $msg
}

function Write-Error-Custom($msg) {
    Write-Host "[ERROR] " -ForegroundColor Red -NoNewline
    Write-Host $msg
}

# Change to project root
Set-Location $PSScriptRoot\..

# ── Check Python version ───────────────────────────────────────
Write-Info "Checking Python version..."

try {
    $PyVersion = & $PythonCmd --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw }
}
catch {
    Write-Error-Custom "Python not found. Install Python >= 3.10 and re-run."
    exit 1
}

$VersionMatch = $PyVersion -match '(\d+)\.(\d+)'
if (-not $VersionMatch) {
    Write-Error-Custom "Could not parse Python version: $PyVersion"
    exit 1
}

$PyMajor = [int]$Matches[1]
$PyMinor = [int]$Matches[2]

if ($PyMajor -lt 3 -or ($PyMajor -eq 3 -and $PyMinor -lt 10)) {
    Write-Error-Custom "Python >= 3.10 required, found $PyMajor.$PyMinor"
    exit 1
}

Write-Info "Python $PyMajor.$PyMinor OK"

# ── Create virtual environment ─────────────────────────────────
if (-not (Test-Path $VenvDir)) {
    Write-Info "Creating virtual environment in $VenvDir ..."
    & $PythonCmd -m venv $VenvDir
}
else {
    Write-Info "Virtual environment $VenvDir already exists, reusing."
}

# Activate
$ActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
if (Test-Path $ActivateScript) {
    & $ActivateScript
    Write-Info "Activated venv ($VenvDir)"
}
else {
    Write-Error-Custom "Could not find activation script: $ActivateScript"
    exit 1
}

# ── Upgrade pip ────────────────────────────────────────────────
Write-Info "Upgrading pip..."
python -m pip install --upgrade pip setuptools wheel --quiet

# ── Install PyTorch ────────────────────────────────────────────
Write-Info "Installing PyTorch..."

# Check if CUDA is available (try importing torch first)
try {
    python -c "import torch; assert torch.cuda.is_available()" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Info "CUDA detected — installing GPU-enabled PyTorch"
    }
}
catch {}

# Install PyTorch (will auto-detect CUDA)
python -m pip install torch torchvision torchaudio --quiet

# ── Install PyTorch Geometric ──────────────────────────────────
Write-Info "Installing PyTorch Geometric..."

$TorchVersion = python -c "import torch; print(torch.__version__.split('+')[0])" 2>$null
$CudaTag = python -c "import torch; print(torch.version.cuda.replace('.','') if torch.cuda.is_available() else 'cpu')" 2>$null

python -m pip install torch-geometric --quiet

# Install PyG extensions
Write-Info "Installing PyG extensions (torch=$TorchVersion, cuda=$CudaTag)..."
$PygUrl = "https://data.pyg.org/whl/torch-${TorchVersion}+${CudaTag}.html"

try {
    python -m pip install torch-scatter torch-sparse torch-cluster torch-spline-conv -f $PygUrl --quiet 2>$null
}
catch {
    Write-Warn "Could not install PyG extensions from $PygUrl"
    Write-Warn "Trying without explicit index (may compile from source)..."
    python -m pip install torch-scatter torch-sparse torch-cluster torch-spline-conv --quiet
}

# ── Install the project ────────────────────────────────────────
Write-Info "Installing trojan-detector package..."
if ($Extras) {
    python -m pip install -e ".[$Extras]" --quiet
}
else {
    python -m pip install -e . --quiet
}

# ── Check Yosys ────────────────────────────────────────────────
try {
    $YosysVer = yosys -V 2>&1 | Select-Object -First 1
    Write-Info "Yosys found: $YosysVer"
}
catch {
    Write-Warn "Yosys not found in PATH."
    Write-Warn "The netlist_synthesizer stage requires Yosys."
    Write-Warn "Install from: https://github.com/YosysHQ/yosys"
    Write-Warn "  Windows: Use WSL, or install oss-cad-suite"
}

# ── Download training datasets ─────────────────────────────────
Write-Info "Setting up training dataset directory structure..."
try {
    python -m backend.training.download_extended_datasets 2>$null
}
catch {
    Write-Warn "Dataset download script failed (non-critical). You can run it later:"
    Write-Warn "  python -m backend.training.download_extended_datasets"
}

# ── Verify installation ────────────────────────────────────────
Write-Info "Verifying installation..."

try {
    python -c @"
import backend.core.pipeline
import backend.trojan_classifier.ensemble
import backend.analysis_summarizer.summarizer
print('  Core pipeline ............. OK')
"@
}
catch {
    Write-Error-Custom "Core package import failed"
    exit 1
}

if ($Extras) {
    try {
        python -c "import PySide6; print('  PySide6 (GUI) ............ OK')" 2>$null
    }
    catch {
        Write-Host "  PySide6 (GUI) ............ SKIP (optional)"
    }

    try {
        python -c "import sklearn, matplotlib; print('  sklearn + matplotlib ..... OK')" 2>$null
    }
    catch {
        Write-Host "  sklearn + matplotlib ..... SKIP (optional)"
    }
}

# ── Done ───────────────────────────────────────────────────────
Write-Host ""
Write-Info "Setup complete!"
Write-Host ""
Write-Host "  Activate the environment:  .\.venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "  Run the detector (CLI):    python -m main <file.v> -o reports\ -f text json"
Write-Host "  Run the detector (GUI):    python -m main"
Write-Host "                             or run:  .\windows\run_gui.bat"
Write-Host ""
Write-Host "  Train models:  see windows\ folder"
Write-Host "    .\windows\train_gcn.bat"
Write-Host "    .\windows\train_gat.bat"
Write-Host "    .\windows\train_gin.bat"
Write-Host "    .\windows\train_all.bat"
Write-Host ""
