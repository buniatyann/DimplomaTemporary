#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# setup.sh — Bootstrap the trojan-detector project.
#
# Usage:
#   ./setup.sh            Install core + GUI + training deps
#   ./setup.sh --core     Install core deps only (no GUI, no training)
#   ./setup.sh --dev      Install everything including dev/test tools
# ──────────────────────────────────────────────────────────────
set -euo pipefail

PYTHON="${PYTHON:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

# ── Colour helpers ────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Parse args ────────────────────────────────────────────────
EXTRAS="gui,training"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --core)  EXTRAS=""; shift ;;
        --dev)   EXTRAS="all"; shift ;;
        *)       error "Unknown flag: $1"; exit 1 ;;
    esac
done

# ── Check Python version ─────────────────────────────────────
info "Checking Python version..."
if ! command -v "$PYTHON" &>/dev/null; then
    error "Python not found. Install Python >= 3.10 and re-run."
    exit 1
fi

PY_VERSION=$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$("$PYTHON" -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$("$PYTHON" -c 'import sys; print(sys.version_info.minor)')

if (( PY_MAJOR < 3 )) || (( PY_MAJOR == 3 && PY_MINOR < 10 )); then
    error "Python >= 3.10 required, found $PY_VERSION"
    exit 1
fi
info "Python $PY_VERSION OK"

# ── Create virtual environment ────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtual environment in $VENV_DIR ..."
    "$PYTHON" -m venv "$VENV_DIR"
else
    info "Virtual environment $VENV_DIR already exists, reusing."
fi

# Activate
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
info "Activated venv ($VENV_DIR)"

# ── Upgrade pip ───────────────────────────────────────────────
info "Upgrading pip..."
pip install --upgrade pip setuptools wheel --quiet

# ── Install PyTorch (with CUDA if available) ──────────────────
info "Installing PyTorch..."
if python -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
    info "CUDA detected — installing GPU-enabled PyTorch"
    pip install torch torchvision torchaudio --quiet
else
    # Try to install with CUDA support first; the user may have a GPU
    # but no torch installed yet to test with.
    pip install torch torchvision torchaudio --quiet
fi

# ── Install PyTorch Geometric + extensions ────────────────────
info "Installing PyTorch Geometric..."
TORCH_VERSION=$(python -c "import torch; print(torch.__version__.split('+')[0])")
CUDA_TAG=$(python -c "import torch; print(torch.version.cuda.replace('.','') if torch.cuda.is_available() else 'cpu')")

pip install torch-geometric --quiet

# torch-sparse, torch-scatter, torch-cluster, torch-spline-conv
# These need to match torch + CUDA versions.
info "Installing PyG extensions (torch=$TORCH_VERSION, cuda=$CUDA_TAG) ..."
PYG_URL="https://data.pyg.org/whl/torch-${TORCH_VERSION}+${CUDA_TAG}.html"
pip install torch-scatter torch-sparse torch-cluster torch-spline-conv \
    -f "$PYG_URL" --quiet 2>/dev/null || {
    warn "Could not install PyG extensions from $PYG_URL"
    warn "Trying without explicit index (may compile from source)..."
    pip install torch-scatter torch-sparse torch-cluster torch-spline-conv --quiet || true
}

# ── Install the project ──────────────────────────────────────
info "Installing trojan-detector package..."
if [ -n "$EXTRAS" ]; then
    pip install -e ".[$EXTRAS]" --quiet
else
    pip install -e . --quiet
fi

# ── Check Yosys ──────────────────────────────────────────────
if command -v yosys &>/dev/null; then
    YOSYS_VER=$(yosys -V 2>&1 | head -1)
    info "Yosys found: $YOSYS_VER"
else
    warn "Yosys not found in PATH."
    warn "The netlist_synthesizer stage requires Yosys. Install it with:"
    warn "  Ubuntu/Debian: sudo apt install yosys"
    warn "  macOS:         brew install yosys"
    warn "  From source:   https://github.com/YosysHQ/yosys"
fi

# ── Download training datasets ───────────────────────────────
info "Setting up training dataset directory structure..."
python -m backend.training.download_extended_datasets 2>/dev/null || {
    warn "Dataset download script failed (non-critical). You can run it later:"
    warn "  python -m backend.training.download_extended_datasets"
}

# ── Verify installation ──────────────────────────────────────
info "Verifying installation..."
python -c "
import backend.core.pipeline
import backend.trojan_classifier.ensemble
import backend.analysis_summarizer.summarizer
print('  Core pipeline ............. OK')
" || { error "Core package import failed"; exit 1; }

if [ "$EXTRAS" != "" ]; then
    python -c "
try:
    import PySide6
    print('  PySide6 (GUI) ............ OK')
except ImportError:
    print('  PySide6 (GUI) ............ SKIP (optional)')
" 2>/dev/null || true

    python -c "
try:
    import sklearn, matplotlib
    print('  sklearn + matplotlib ..... OK')
except ImportError:
    print('  sklearn + matplotlib ..... SKIP (optional)')
" 2>/dev/null || true
fi

# ── Done ──────────────────────────────────────────────────────
echo ""
info "Setup complete!"
echo ""
echo "  Activate the environment:  source $VENV_DIR/bin/activate"
echo ""
echo "  Run the detector (CLI):    python -m main <file.v> -o reports/ -f text json"
echo "  Run the detector (GUI):    python -m main"
echo ""
echo "  Train models:  see training_scripts/ folder"
echo "    ./training_scripts/train_gcn.sh"
echo "    ./training_scripts/train_gat.sh"
echo "    ./training_scripts/train_gin.sh"
echo "    ./training_scripts/train_all.sh"
echo ""
