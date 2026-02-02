#!/usr/bin/env bash
# Download publicly available training datasets (ISCAS, EPFL) and
# create the folder structure for manual TrustHub/TRIT placement.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "Downloading and setting up training datasets..."
python -m backend.training.download_extended_datasets
