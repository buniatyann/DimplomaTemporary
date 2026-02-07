@echo off
REM Train GCN architecture on TrustHub + TRIT + ISCAS + EPFL datasets.
REM Weights are saved to: backend\trojan_classifier\weights\gcn_weights.pt

cd /d "%~dp0\.."

echo ================================================
echo   Training GCN Architecture
echo ================================================
echo.

if not exist ".venv\" (
    echo [ERROR] Virtual environment not found! Run windows\setup.ps1 first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

python -m backend.training.train_local ^
    --architecture gcn ^
    --epochs 200 ^
    --hidden-dim 128 ^
    --num-layers 4 ^
    --lr 1e-3 ^
    --weight-decay 1e-2 ^
    --dropout 0.3 ^
    --batch-size 32 ^
    --patience 30 ^
    --augment ^
    --oversample ^
    --seed 42 ^
    -vv ^
    %*

echo.
echo Training complete. Weights saved to:
echo   backend\trojan_classifier\weights\gcn_weights.pt
echo.
pause
