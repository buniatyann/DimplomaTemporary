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

# ── Install PyTorch ───────────────────────────────────────────
# pip will fetch the CUDA-enabled wheel automatically when a compatible
# GPU + driver is detected. torchvision/torchaudio aren't used anywhere
# in the project, so they're skipped.
info "Installing PyTorch..."
pip install torch

# ── Install the project (pulls torch-geometric + remaining deps) ─
# torch-geometric ≥2.3 bundles its own scatter/sparse ops, so the old
# torch-scatter/torch-sparse/torch-cluster/torch-spline-conv wheels are
# no longer required.
info "Installing trojan-detector package..."
if [ -n "$EXTRAS" ]; then
    pip install -e ".[$EXTRAS]"
else
    pip install -e .
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
echo "  Training datasets:  fetched separately (see backend/training/data/README.md)"
echo ""
echo "  Train models:  see training_scripts/ folder"
echo "    ./training_scripts/train_gcn.sh"
echo "    ./training_scripts/train_gat.sh"
echo "    ./training_scripts/train_gin.sh"
echo "    ./training_scripts/train_all.sh"
echo ""
