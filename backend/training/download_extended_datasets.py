#!/usr/bin/env python3
"""
Downloads additional datasets from GitHub repositories.
Manual downloads required for TrustHub and TRIT.
"""

import subprocess
import shutil
from pathlib import Path

DATA_ROOT = Path(__file__).parent / "data"

def create_folder_structure():
    """Create all required directories."""
    folders = [
        "trusthub/raw/saed90nm/aes",
        "trusthub/raw/saed90nm/rs232",
        "trusthub/raw/saed90nm/basicrsa",
        "trusthub/raw/saed90nm/sha256",
        "trusthub/raw/saed90nm/s15850",
        "trusthub/raw/saed90nm/labels",
        "trusthub/raw/leda250nm/aes",
        "trusthub/raw/leda250nm/rs232",
        "trusthub/raw/leda250nm/labels",
        "trusthub/processed/training/graphs",
        "trusthub/processed/training/metadata",
        "trusthub/processed/validation/graphs",
        "trusthub/processed/validation/metadata",
        "trusthub/processed/verification/graphs",
        "trusthub/processed/verification/metadata",
        "trit/raw/leda250nm/trit_tc/c2670",
        "trit/raw/leda250nm/trit_tc/c3540",
        "trit/raw/leda250nm/trit_tc/c5315",
        "trit/raw/leda250nm/trit_tc/c6288",
        "trit/raw/leda250nm/trit_ts/s1423",
        "trit/raw/leda250nm/trit_ts/s13207",
        "trit/raw/leda250nm/trit_ts/s15850",
        "trit/raw/leda250nm/trit_ts/s35932",
        "trit/raw/leda250nm/labels",
        "trit/raw/skywater130nm/trit_tc",
        "trit/raw/skywater130nm/trit_ts/s953",
        "trit/raw/skywater130nm/trit_ts/s1196",
        "trit/raw/skywater130nm/trit_ts/s1238",
        "trit/raw/skywater130nm/trit_ts/s1423",
        "trit/raw/skywater130nm/trit_ts/s1488",
        "trit/raw/skywater130nm/trit_ts/s5378",
        "trit/raw/skywater130nm/trit_ts/s9234",
        "trit/raw/skywater130nm/trit_ts/s38417",
        "trit/raw/skywater130nm/trit_ts/s38584",
        "trit/raw/skywater130nm/labels",
        "trit/processed",
        "iscas/iscas85",
        "iscas/iscas89",
        "epfl/arithmetic",
        "epfl/random_control",
        "itc99",
        "opencores/processors",
        "opencores/crypto",
        "opencores/communication",
        "cell_libraries/saed90nm",
        "cell_libraries/leda250nm",
        "cell_libraries/skywater130nm",
        "configs",
        "metadata",
    ]

    for folder in folders:
        (DATA_ROOT / folder).mkdir(parents=True, exist_ok=True)
        readme = DATA_ROOT / folder / ".gitkeep"
        readme.touch()

    print(f"Created {len(folders)} directories")

def clone_github_repo(url: str, dest: Path):
    """Clone a GitHub repository."""
    if dest.exists():
        print(f"Skipping {dest.name}, already exists")
        return

    print(f"Cloning {url}...")
    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)],
        check=True
    )

def download_ispras_benchmarks():
    """Download ISCAS benchmarks from ISPRAS collection."""
    temp_dir = DATA_ROOT / "_temp" / "ispras"
    clone_github_repo(
        "https://github.com/ispras/hdl-benchmarks",
        temp_dir
    )

    # Copy ISCAS'85 Verilog files
    iscas85_src = temp_dir / "iscas85" / "verilog"
    iscas85_dst = DATA_ROOT / "iscas" / "iscas85"
    if iscas85_src.exists():
        for f in iscas85_src.glob("*.v"):
            shutil.copy(f, iscas85_dst / f.name)
        print(f"Copied ISCAS'85 files to {iscas85_dst}")

    # Copy ISCAS'89 Verilog files
    iscas89_src = temp_dir / "iscas89" / "verilog"
    iscas89_dst = DATA_ROOT / "iscas" / "iscas89"
    if iscas89_src.exists():
        for f in iscas89_src.glob("*.v"):
            shutil.copy(f, iscas89_dst / f.name)
        print(f"Copied ISCAS'89 files to {iscas89_dst}")

def download_epfl_benchmarks():
    """Download EPFL benchmarks."""
    temp_dir = DATA_ROOT / "_temp" / "epfl"
    clone_github_repo(
        "https://github.com/lsils/benchmarks",
        temp_dir
    )

    # Copy arithmetic benchmarks
    arith_src = temp_dir / "arithmetic"
    arith_dst = DATA_ROOT / "epfl" / "arithmetic"
    if arith_src.exists():
        for f in arith_src.glob("*.v"):
            shutil.copy(f, arith_dst / f.name)
        print(f"Copied EPFL arithmetic files to {arith_dst}")

    # Copy random_control benchmarks
    ctrl_src = temp_dir / "random_control"
    ctrl_dst = DATA_ROOT / "epfl" / "random_control"
    if ctrl_src.exists():
        for f in ctrl_src.glob("*.v"):
            shutil.copy(f, ctrl_dst / f.name)
        
        print(f"Copied EPFL control files to {ctrl_dst}")

def cleanup_temp():
    """Remove temporary download directory."""
    temp_dir = DATA_ROOT / "_temp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
        print("Cleaned up temporary files")

def print_manual_instructions():
    """Print instructions for manual downloads."""
    instructions = """
================================================================================
MANUAL DOWNLOAD REQUIRED
================================================================================

The following datasets require manual download:

1. TrustHub Benchmarks:
   URL: https://trust-hub.org/#/benchmarks
   - Register for account if needed
   - Download gate-level benchmarks for SAED 90nm
   - Download gate-level benchmarks for LEDA 250nm
   - Place trojan files (e.g., AES-T100.v) in:
       backend/training/data/trusthub/raw/saed90nm/aes/
   - Place golden files (e.g., AES_golden.v) in same folders

2. TRIT Synthetic Benchmarks:
   URL: https://cadforassurance.org/benchmarks/synthetic-trojan-inserted-asic-benchmarks/
   - Download TRIT-TC (combinational) for LEDA 250nm
   - Download TRIT-TS (sequential) for LEDA 250nm
   - Download TRIT benchmarks for Skywater 130nm
   - Each ZIP includes golden (clean) circuits
   - Place in: backend/training/data/trit/raw/

3. ITC'99 Benchmarks (optional, for verification):
   URL: https://www.cerc.utexas.edu/itc99-benchmarks/
   - Download Verilog gate-level versions
   - Place in: backend/training/data/itc99/

4. OpenCores (optional, for verification):
   URL: https://opencores.org
   - Download IP cores as needed
   - Place in: backend/training/data/opencores/

================================================================================
DATASET PURPOSE
================================================================================

TRAINING (use these to train the model):
- trusthub/raw/saed90nm/* (trojan + golden)
- trit/raw/leda250nm/* (trojan + golden)
- iscas/* (clean circuits)
- epfl/* (clean circuits)

VERIFICATION (hold out, use only for final testing):
- trusthub/raw/leda250nm/* (different cell library)
- trit/raw/skywater130nm/* (different process node)
- itc99/* (clean industrial circuits)
- opencores/* (real-world clean circuits)

================================================================================
"""
    print(instructions)

def main():
    print("Setting up extended dataset structure...")
    print(f"Data root: {DATA_ROOT}")
    print()

    # Step 1: Create folder structure
    print("Step 1: Creating folder structure...")
    create_folder_structure()
    print()

    # Step 2: Download GitHub-hosted datasets
    print("Step 2: Downloading GitHub-hosted datasets...")
    try:
        download_ispras_benchmarks()
    except Exception as e:
        print(f"Warning: Could not download ISPRAS benchmarks: {e}")

    try:
        download_epfl_benchmarks()
    except Exception as e:
        print(f"Warning: Could not download EPFL benchmarks: {e}")
    print()

    # Step 3: Cleanup
    print("Step 3: Cleaning up...")
    cleanup_temp()
    print()

    # Step 4: Print manual instructions
    print_manual_instructions()

    # Step 5: Summary
    print("Step 4: Verifying structure...")
    verilog_count = len(list(DATA_ROOT.rglob("*.v")))
    print(f"Total Verilog files found: {verilog_count}")
    print()
    print("Setup complete. Follow manual instructions above to add remaining datasets.")

if __name__ == "__main__":
    main()
