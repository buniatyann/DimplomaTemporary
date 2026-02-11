# Hardware Trojan Detector

Automated detection of hardware trojans in gate-level Verilog and SystemVerilog netlists using Graph Neural Networks (GNNs).

The tool processes HDL source files through a 6-stage pipeline — from file ingestion to synthesis, graph construction, GNN-based classification, and report generation — to identify malicious logic inserted into integrated circuits. It provides per-gate suspicion scores and exact source locations of detected trojans.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Pipeline Architecture](#pipeline-architecture)
- [GNN Models](#gnn-models)
- [Training](#training)
  - [Training Data Sources](#training-data-sources)
- [GUI](#gui)
- [Project Structure](#project-structure)
- [Development](#development)
- [License](#license)

## Features

- **Multi-format parsing** — supports Verilog (`.v`, `.vh`) via pyverilog and SystemVerilog (`.sv`) via pyslang
- **Yosys-based synthesis** — elaborates netlists into a normalized JSON representation
- **Graph Neural Network classification** — three interchangeable architectures (GCN, GAT, GIN) with pretrained weights
- **Trojan localization** — reports suspicious gates with exact `file:line` source locations
- **Multiple export formats** — JSON, PDF, and plain text reports
- **CLI and GUI interfaces** — command-line pipeline and PySide6 desktop application
- **Batch processing** — analyze entire directories of HDL files independently
- **CUDA support** — automatic GPU detection for accelerated inference

## Requirements

- Python >= 3.10
- [Yosys](https://github.com/YosysHQ/yosys) — must be installed and available in `PATH`
- CUDA-capable GPU (optional, for faster inference)

## Installation

### Linux / macOS

```bash
git clone <repository-url>
cd trojan-detector

# Automated setup (creates venv, installs dependencies, downloads datasets)
./setup.sh            # Full install (core + GUI + training)
./setup.sh --core     # Core pipeline only
./setup.sh --dev      # Everything + development tools
```

### Manual installation

```bash
python -m venv .venv
source .venv/bin/activate

pip install -e "."            # Core dependencies
pip install -e ".[gui]"       # Add GUI support
pip install -e ".[training]"  # Add training dependencies
pip install -e ".[dev]"       # Add development tools
pip install -e ".[all]"       # Everything
```

### Windows

See [windows/README.md](windows/README.md) for Windows-specific setup instructions and PowerShell scripts.

## Usage

### CLI

```bash
# Analyze a single file
python -m main circuit.v -o reports/ -f json text pdf

# Analyze a directory
python -m main designs/ -o reports/

# Batch mode (process each file independently)
python -m main designs/ --batch -o reports/

# Choose GNN architecture
python -m main circuit.v -a gat

# Adjust confidence threshold
python -m main circuit.v -t 0.85

# Force CPU execution
python -m main circuit.v --device cpu

# Verbose output
python -m main circuit.v -v    # INFO level
python -m main circuit.v -vv   # DEBUG level
```

### Full CLI reference

```
trojan-detector [input] [-o OUTPUT_DIR] [-f FORMAT...] [-a ARCH] [-t THRESHOLD]
                        [--device DEVICE] [--batch] [-v|-vv]

positional arguments:
  input                   Path to a Verilog file or directory. Omit to launch the GUI.

options:
  -o, --output-dir DIR    Directory for report output (default: current directory)
  -f, --format FMT        Export format(s): json, pdf, text (default: json)
  -a, --architecture ARCH GNN architecture: gcn, gat, gin (default: gcn)
  -t, --confidence-threshold N
                          Confidence threshold for classification (default: 0.7)
  --device DEVICE         Computation device: cpu, cuda, cuda:N (default: auto-detect)
  --batch                 Process all files in directory independently
  -v, --verbose           Increase verbosity (-v INFO, -vv DEBUG)
```

### GUI

```bash
# Launch the graphical interface
python -m main
```

The GUI provides file selection, real-time progress, log viewing, and report preview.

## Pipeline Architecture

The detection system is a sequential 6-stage pipeline. Each stage receives a shared `History` object for inter-stage communication and returns a `StageOutcome[T]` indicating success or failure. The pipeline stops at the first failure but always runs the final stage to produce at least a partial report.

```
Input (.v / .sv / .vh)
        |
        v
+-------------------+
| 1. File Ingestion | --> DirectoryManifest (discovered files, checksums)
+-------------------+
        |
        v
+-------------------+
| 2. Syntax Parser  | --> list[ParsedModule] (gates, wires, ports)
+-------------------+
        |
        v
+-------------------+
| 3. Netlist         | --> SynthesisResult (Yosys JSON netlist)
|    Synthesizer     |
+-------------------+
        |
        v
+-------------------+
| 4. Graph Builder  | --> CircuitGraph (PyTorch Geometric Data object)
+-------------------+
        |
        v
+-------------------+
| 5. Trojan          | --> ClassificationResult (verdict, confidence,
|    Classifier      |     per-node scores, trojan locations)
+-------------------+
        |
        v
+-------------------+
| 6. Analysis        | --> AnalysisReport (JSON / PDF / text)
|    Summarizer      |
+-------------------+
```

## GNN Models

Three graph neural network architectures are available, all sharing the same interface:

| Architecture | Description | Strengths |
|---|---|---|
| **GCN** (default) | Graph Convolutional Network | Fast inference, good general performance |
| **GAT** | Graph Attention Network | Attention-based; better at capturing local structure |
| **GIN** | Graph Isomorphism Network | Most expressive; best at distinguishing graph structures |

All models use:
- 4 convolutional layers with batch normalization and residual connections
- 128-dimensional hidden representations
- 17-dimensional node feature vectors (gate type, fan-in/fan-out, hierarchy position)
- Dual output heads: graph-level classification (trojan vs. clean) and node-level suspicion scoring

Pretrained weights are stored in `backend/trojan_classifier/weights/`.

## Training

Train GNN models on the TrustHub hardware trojan benchmark suite:

```bash
# Train individual architectures
python -m backend.training.train --data-dir ./data/trusthub --architecture gcn
python -m backend.training.train --data-dir ./data/trusthub --architecture gat --epochs 100
python -m backend.training.train --data-dir ./data/trusthub --architecture gin --batch-size 16

# Or use the training scripts
./training_scripts/train_all.sh    # Train all three models
./training_scripts/train_gcn.sh    # Train GCN only
```

### Training data sources

Training and evaluation use publicly available hardware trojan benchmarks and clean circuit collections:

| Dataset | Description | Link | Download |
|---|---|---|---|
| **TrustHub** | Chip-level hardware trojan benchmarks (trojan + golden pairs) | [trust-hub.org](https://trust-hub.org/#/benchmarks/chip-level-trojan) | Manual (registration required) |
| **TRIT** | Synthetic trojan-inserted ASIC benchmarks (LEDA 250nm, Skywater 130nm) | [cadforassurance.org](https://cadforassurance.org/benchmarks/synthetic-trojan-inserted-asic-benchmarks/) | Manual |
| **ISCAS'85 / ISCAS'89** | Combinational and sequential benchmark circuits (clean) | [github.com/ispras/hdl-benchmarks](https://github.com/ispras/hdl-benchmarks) | Automatic (`git clone`) |
| **EPFL Benchmarks** | Arithmetic and random-control circuits (clean) | [github.com/lsils/benchmarks](https://github.com/lsils/benchmarks) | Automatic (`git clone`) |
| **ITC'99** | Industrial test circuits (clean, verification set) | [cerc.utexas.edu/itc99-benchmarks](https://www.cerc.utexas.edu/itc99-benchmarks/) | Manual |
| **OpenCores** | Real-world open-source IP cores (clean, verification set) | [opencores.org](https://opencores.org) | Manual |

**TrustHub benchmarks** provide the primary trojan-infected training data, each paired with a golden (trojan-free) reference:

- **AES** — AES-T100 through AES-T2000 (cryptographic trojans)
- **RS232** — RS232-T100 through RS232-T500 (UART trojans)
- **PIC16F84** — Microcontroller trojans
- **wb_conmax** — Wishbone interconnect trojans
- **BasicRSA** — RSA cryptographic core trojans
- **ISCAS'89** — s38417, s35932, s15850 benchmark trojans

**ISCAS and EPFL** circuits serve as clean (trojan-free) samples for balanced training. **ITC'99 and OpenCores** are held out for independent verification.

To download the automatically available datasets:

```bash
./training_scripts/download_datasets.sh
```

TrustHub and TRIT require manual download after registration. See [backend/training/data/README.md](backend/training/data/README.md) for the expected directory layout.

### Training hyperparameters

| Parameter | Default |
|---|---|
| Epochs | 200 |
| Hidden dimension | 128 |
| Layers | 4 |
| Learning rate | 1e-3 |
| Weight decay | 1e-2 |
| Dropout | 0.3 |
| Batch size | 32 |
| Early stopping patience | 30 |

## GUI

The PySide6-based graphical interface provides:

- File and directory selection for analysis
- Real-time pipeline progress and status reporting
- Interactive log viewer
- Report preview in all export formats
- Settings panel for architecture, confidence threshold, and device selection
- Asynchronous processing with cancellation support

Install GUI dependencies:

```bash
pip install -e ".[gui]"
```

## Project Structure

```
.
├── backend/
│   ├── core/                       # Pipeline orchestration, History, StageOutcome
│   ├── file_ingestion/             # Stage 1: file discovery and validation
│   ├── syntax_parser/              # Stage 2: Verilog/SystemVerilog parsing
│   ├── netlist_synthesizer/        # Stage 3: Yosys synthesis
│   ├── netlist_graph_builder/      # Stage 4: graph construction
│   ├── trojan_classifier/          # Stage 5: GNN classification
│   │   ├── architectures/          # GCN, GAT, GIN implementations
│   │   └── weights/                # Pretrained model weights
│   ├── analysis_summarizer/        # Stage 6: report generation
│   │   └── exporters/              # JSON, PDF, text exporters
│   ├── api/                        # DetectorAPI facade for external consumers
│   └── training/                   # Dataset loading, labeling, training loop
├── gui/                            # PySide6 desktop application
├── tests/                          # pytest test suite
├── training_scripts/               # Shell scripts for model training
├── windows/                        # Windows setup and batch scripts
├── main.py                         # CLI / GUI entry point
├── config.py                       # Global configuration
├── pyproject.toml                  # Project metadata and dependencies
└── setup.sh                        # Automated setup script
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/
pytest tests/test_file_ingestion/                                          # single module
pytest tests/test_file_ingestion/test_collector.py                         # single file
pytest tests/test_file_ingestion/test_collector.py::TestCollector::test_single_file  # single test

# Lint
ruff check .

# Type check
mypy backend/
```

## License

MIT License. See [LICENSE](LICENSE) for details.
