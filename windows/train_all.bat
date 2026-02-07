@echo off
REM Train all three architectures sequentially (GCN → GIN → GAT).
REM Each produces a separate weights file used by the EnsembleClassifier.
REM
REM Weights saved to:
REM   backend\trojan_classifier\weights\gcn_weights.pt
REM   backend\trojan_classifier\weights\gin_weights.pt
REM   backend\trojan_classifier\weights\gat_weights.pt

cd /d "%~dp0"

echo ================================================
echo   Training all architectures for ensemble
echo ================================================
echo.

echo [1/3] Training GCN ...
call train_gcn.bat %*
echo.

echo [2/3] Training GIN ...
call train_gin.bat %*
echo.

echo [3/3] Training GAT ...
call train_gat.bat %*
echo.

echo ================================================
echo   All architectures trained.
echo   Weights directory:
echo     backend\trojan_classifier\weights\
echo ================================================
echo.

dir /b "..\backend\trojan_classifier\weights\*.pt" 2>nul
if errorlevel 1 (
    echo   (no weight files found)
)

echo.
pause
