#!/usr/bin/env bash
# Train all three architectures sequentially (GCN → GIN → GAT).
# Each produces a separate weights file used by the EnsembleClassifier.
#
# Weights saved to:
#   backend/trojan_classifier/weights/gcn_weights.pt
#   backend/trojan_classifier/weights/gin_weights.pt
#   backend/trojan_classifier/weights/gat_weights.pt
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================"
echo " Training all architectures for ensemble"
echo "============================================"
echo ""

echo ">>> [1/3] Training GCN ..."
bash "$SCRIPT_DIR/train_gcn.sh" "$@"
echo ""

echo ">>> [2/3] Training GIN ..."
bash "$SCRIPT_DIR/train_gin.sh" "$@"
echo ""

echo ">>> [3/3] Training GAT ..."
bash "$SCRIPT_DIR/train_gat.sh" "$@"
echo ""

echo "============================================"
echo " All architectures trained."
echo " Weights directory:"
echo "   backend/trojan_classifier/weights/"
echo "============================================"
ls -lh "$(dirname "$SCRIPT_DIR")/backend/trojan_classifier/weights/"*.pt 2>/dev/null || echo "  (no weight files found)"
