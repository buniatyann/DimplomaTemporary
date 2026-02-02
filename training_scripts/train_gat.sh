#!/usr/bin/env bash
# Train GAT architecture on TrustHub + TRIT + ISCAS + EPFL datasets.
# Weights are saved to: backend/trojan_classifier/weights/gat_weights.pt
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

python -m backend.training.train_local \
    --architecture gat \
    --epochs 200 \
    --hidden-dim 128 \
    --num-layers 4 \
    --lr 1e-3 \
    --weight-decay 1e-2 \
    --dropout 0.3 \
    --batch-size 32 \
    --patience 30 \
    --augment \
    --oversample \
    --seed 42 \
    -vv \
    "$@"
