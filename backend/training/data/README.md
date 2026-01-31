# Training Data Directory

## Structure

```
data/
├── trusthub/          # Primary trojan benchmarks (TRAINING + VERIFICATION)
│   ├── raw/
│   │   ├── saed90nm/  # TRAINING - trojan + golden circuits
│   │   └── leda250nm/ # VERIFICATION - different cell library
│   └── processed/     # Preprocessed PyG graph files
│
├── trit/              # TRIT synthetic trojans (TRAINING + VERIFICATION)
│   ├── raw/
│   │   ├── leda250nm/     # TRAINING
│   │   └── skywater130nm/ # VERIFICATION
│   └── processed/
│
├── iscas/             # TRAINING - clean circuits
│   ├── iscas85/       # 11 combinational circuits
│   └── iscas89/       # 31 sequential circuits
│
├── epfl/              # TRAINING - clean circuits
│   ├── arithmetic/    # 10 arithmetic circuits
│   └── random_control/ # 10 control circuits
│
├── itc99/             # VERIFICATION - clean industrial circuits
│
├── opencores/         # VERIFICATION - real-world clean circuits
│
├── cell_libraries/    # Standard cell library files
│
├── configs/           # Dataset configuration files
│
└── metadata/          # Dataset statistics and manifests
```

## Dataset Sources

| Dataset | URL | Purpose |
|---------|-----|---------|
| TrustHub | https://trust-hub.org/#/benchmarks | Primary trojans |
| TRIT | https://cadforassurance.org/benchmarks/synthetic-trojan-inserted-asic-benchmarks/ | Synthetic trojans |
| ISCAS | https://github.com/ispras/hdl-benchmarks | Clean circuits |
| EPFL | https://github.com/lsils/benchmarks | Clean circuits |
| ITC'99 | https://www.cerc.utexas.edu/itc99-benchmarks/ | Verification |
| OpenCores | https://opencores.org | Verification |

## Usage

1. Run `python -m backend.training.download_extended_datasets`
2. Manually download TrustHub and TRIT (requires registration)
3. Place files in appropriate directories
4. Run training: `python -m backend.training.train`

## File Naming Convention

- Trojan circuits: `{DESIGN}-T{NUMBER}.v` (e.g., `AES-T100.v`)
- Golden circuits: `{DESIGN}_golden.v` (e.g., `AES_golden.v`)
- TRIT trojans: `{CIRCUIT}_trojan_{NUMBER}.v` (e.g., `c2670_trojan_001.v`)
- TRIT golden: `{CIRCUIT}_golden.v` (e.g., `c2670_golden.v`)
- Labels: `{NETLIST_NAME}_labels.json`

## Label Format

```json
{
    "netlist_name": "AES-T100",
    "cell_library": "saed90nm",
    "trojan_type": "information_leakage",
    "total_gates": 15847,
    "trojan_gates": 42,
    "trojan_gate_names": ["U1234", "U1235", "U1236"]
}
```
