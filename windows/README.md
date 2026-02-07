# Windows Scripts

This folder contains Windows-specific scripts for the Hardware Trojan Detector project.

## Quick Start

### 1. Install Dependencies

Run the setup script in PowerShell:

```powershell
.\setup.ps1
```

**Options:**
- `.\setup.ps1` - Install core + GUI + training dependencies (recommended)
- `.\setup.ps1 -Core` - Install core dependencies only (no GUI, no training tools)
- `.\setup.ps1 -Dev` - Install everything including development and testing tools

### 2. Activate Virtual Environment

After setup completes:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Run the Application

**Launch GUI:**
```batch
.\run_gui.bat
```

**Run CLI:**
```batch
python -m main <path\to\file.v> -o reports\ -f json text pdf
```

### 4. Train Models

**Train individual models:**
```batch
.\train_gcn.bat  # Train Graph Convolutional Network
.\train_gat.bat  # Train Graph Attention Network
.\train_gin.bat  # Train Graph Isomorphism Network
```

**Train all models sequentially:**
```batch
.\train_all.bat  # Trains GCN → GIN → GAT
```

## Script Descriptions

| Script | Description |
|--------|-------------|
| `setup.ps1` | PowerShell installation script that sets up Python environment, installs dependencies, and verifies installation |
| `run_gui.bat` | Launches the PySide6 GUI application |
| `train_gcn.bat` | Trains the GCN model with optimized hyperparameters (200 epochs) |
| `train_gat.bat` | Trains the GAT model with optimized hyperparameters (200 epochs) |
| `train_gin.bat` | Trains the GIN model with optimized hyperparameters (200 epochs) |
| `train_all.bat` | Trains all three models sequentially for ensemble classification |

## Requirements

- **Python 3.10 or higher** - [Download](https://www.python.org/downloads/)
- **Yosys** (for netlist synthesis):
  - Option 1: Use WSL (Windows Subsystem for Linux)
  - Option 2: Install [oss-cad-suite](https://github.com/YosysHQ/oss-cad-suite-build)
- **CUDA** (optional) - For GPU-accelerated training

## Training Details

All training scripts use the following hyperparameters:
- Epochs: 200
- Hidden dimension: 128
- Number of layers: 4
- Learning rate: 1e-3
- Weight decay: 1e-2
- Dropout: 0.3
- Batch size: 32
- Early stopping patience: 30
- Data augmentation: Enabled
- Class oversampling: Enabled

Trained model weights are saved to:
- `backend\trojan_classifier\weights\gcn_weights.pt`
- `backend\trojan_classifier\weights\gat_weights.pt`
- `backend\trojan_classifier\weights\gin_weights.pt`

## Troubleshooting

### PowerShell Execution Policy

If you get an error about execution policy when running `setup.ps1`:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Virtual Environment Not Found

If scripts report missing virtual environment:
1. Run `.\setup.ps1` first
2. Ensure `.venv\` folder exists in project root

### PySide6 Not Found

If GUI fails to launch:
```powershell
.\.venv\Scripts\Activate.ps1
pip install trojan-detector[gui]
```

### CUDA Not Detected

The setup script will automatically detect CUDA. If you have a GPU but CUDA isn't detected:
1. Ensure NVIDIA drivers are installed
2. Install CUDA Toolkit from [NVIDIA](https://developer.nvidia.com/cuda-downloads)
3. Rerun setup: `.\setup.ps1`

## Additional Resources

- [Main README](../README.md)
- [CLAUDE.md](../CLAUDE.md) - Development documentation
- [Training Data README](../backend/training/data/README.md)
