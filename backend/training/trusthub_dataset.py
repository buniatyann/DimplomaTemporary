"""TrustHub benchmark dataset loader for training GNN trojan detectors.

This module handles downloading, processing, and loading TrustHub chip-level
trojan benchmarks that have BOTH trojan-infected AND trojan-free versions.

Supported benchmarks with paired trojan/golden versions:
- AES: AES-T100 through AES-T2000 (cryptographic)
- RS232: RS232-T100 through RS232-T1000 (UART communication)
- PIC16F84: Microcontroller trojans
- wb_conmax: Wishbone interconnect
- BasicRSA: RSA cryptographic core
- s38417, s35932, s15850: ISCAS'89 benchmark circuits
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterator
from urllib.request import urlretrieve

import torch
from torch_geometric.data import Data, Dataset

logger = logging.getLogger(__name__)


class BenchmarkFamily(Enum):
    """Supported TrustHub benchmark families with paired trojan/golden versions."""
    AES = "aes"
    RS232 = "rs232"
    PIC16F84 = "pic16f84"
    WB_CONMAX = "wb_conmax"
    BASIC_RSA = "basicrsa"
    S38417 = "s38417"
    S35932 = "s35932"
    S15850 = "s15850"


@dataclass
class TrustHubBenchmark:
    """Represents a single TrustHub benchmark with trojan and golden versions.

    Attributes:
        name: Benchmark identifier (e.g., "AES-T100")
        family: Benchmark family (e.g., BenchmarkFamily.AES)
        trojan_path: Path to trojan-infected Verilog file(s)
        golden_path: Path to trojan-free golden reference file(s)
        trojan_nets: Set of net/signal names that are part of the trojan
        trojan_modules: Set of module names containing trojan logic
        description: Human-readable description of the trojan type
    """
    name: str
    family: BenchmarkFamily
    trojan_path: Path | None = None
    golden_path: Path | None = None
    trojan_nets: set[str] = field(default_factory=set)
    trojan_modules: set[str] = field(default_factory=set)
    trojan_instances: set[str] = field(default_factory=set)
    description: str = ""

    @property
    def has_both_versions(self) -> bool:
        """Check if both trojan and golden versions are available."""
        return (
            self.trojan_path is not None
            and self.golden_path is not None
            and self.trojan_path.exists()
            and self.golden_path.exists()
        )


# TrustHub benchmark definitions with known trojan/golden pairs
TRUSTHUB_BENCHMARKS: dict[str, dict[str, Any]] = {
    # AES Trojans - T100 series (combinational trojans)
    "AES-T100": {
        "family": BenchmarkFamily.AES,
        "description": "Combinational Trojan leaking key via rarely-triggered condition",
        "trojan_pattern": r"Trojan_Trigger|trojan|Tj_",
    },
    "AES-T200": {
        "family": BenchmarkFamily.AES,
        "description": "Sequential Trojan with counter-based trigger",
        "trojan_pattern": r"Trojan|counter|trigger",
    },
    "AES-T300": {
        "family": BenchmarkFamily.AES,
        "description": "Trojan activated by specific plaintext pattern",
        "trojan_pattern": r"Trojan|trigger|payload",
    },
    "AES-T400": {
        "family": BenchmarkFamily.AES,
        "description": "Hybrid Trojan with multiple trigger conditions",
        "trojan_pattern": r"Trojan|trig|TSC",
    },
    "AES-T500": {
        "family": BenchmarkFamily.AES,
        "description": "Trojan corrupting encryption output",
        "trojan_pattern": r"Trojan|corrupt|fault",
    },
    "AES-T600": {
        "family": BenchmarkFamily.AES,
        "description": "Side-channel leakage Trojan",
        "trojan_pattern": r"Trojan|leak|side",
    },
    "AES-T700": {
        "family": BenchmarkFamily.AES,
        "description": "Denial-of-service Trojan",
        "trojan_pattern": r"Trojan|dos|block",
    },
    "AES-T800": {
        "family": BenchmarkFamily.AES,
        "description": "Key extraction Trojan via covert channel",
        "trojan_pattern": r"Trojan|key|extract",
    },
    "AES-T900": {
        "family": BenchmarkFamily.AES,
        "description": "Time-bomb Trojan with delayed activation",
        "trojan_pattern": r"Trojan|timer|bomb|delay",
    },
    "AES-T1000": {
        "family": BenchmarkFamily.AES,
        "description": "Analog Trojan affecting power consumption",
        "trojan_pattern": r"Trojan|analog|power",
    },

    # RS232 Trojans
    "RS232-T100": {
        "family": BenchmarkFamily.RS232,
        "description": "UART Trojan leaking transmitted data",
        "trojan_pattern": r"Trojan|leak|uart",
    },
    "RS232-T200": {
        "family": BenchmarkFamily.RS232,
        "description": "Baud rate manipulation Trojan",
        "trojan_pattern": r"Trojan|baud|rate",
    },
    "RS232-T300": {
        "family": BenchmarkFamily.RS232,
        "description": "Data corruption Trojan",
        "trojan_pattern": r"Trojan|corrupt|data",
    },
    "RS232-T400": {
        "family": BenchmarkFamily.RS232,
        "description": "Buffer overflow trigger Trojan",
        "trojan_pattern": r"Trojan|buffer|overflow",
    },
    "RS232-T500": {
        "family": BenchmarkFamily.RS232,
        "description": "Covert channel Trojan",
        "trojan_pattern": r"Trojan|covert|channel",
    },

    # PIC16F84 Trojans
    "PIC16F84-T100": {
        "family": BenchmarkFamily.PIC16F84,
        "description": "Microcontroller instruction corruption",
        "trojan_pattern": r"Trojan|instr|corrupt",
    },
    "PIC16F84-T200": {
        "family": BenchmarkFamily.PIC16F84,
        "description": "Program counter manipulation",
        "trojan_pattern": r"Trojan|pc|jump",
    },

    # Wishbone interconnect Trojans
    "wb_conmax-T100": {
        "family": BenchmarkFamily.WB_CONMAX,
        "description": "Bus arbitration Trojan",
        "trojan_pattern": r"Trojan|arb|grant",
    },
    "wb_conmax-T200": {
        "family": BenchmarkFamily.WB_CONMAX,
        "description": "Address decoding Trojan",
        "trojan_pattern": r"Trojan|addr|decode",
    },

    # BasicRSA Trojans
    "BasicRSA-T100": {
        "family": BenchmarkFamily.BASIC_RSA,
        "description": "RSA key leakage Trojan",
        "trojan_pattern": r"Trojan|key|rsa",
    },
    "BasicRSA-T200": {
        "family": BenchmarkFamily.BASIC_RSA,
        "description": "Modular exponentiation fault",
        "trojan_pattern": r"Trojan|exp|fault",
    },

    # ISCAS'89 Benchmark Trojans
    "s38417-T100": {
        "family": BenchmarkFamily.S38417,
        "description": "Sequential circuit Trojan",
        "trojan_pattern": r"Trojan|seq|trig",
    },
    "s35932-T100": {
        "family": BenchmarkFamily.S35932,
        "description": "Combinational Trojan insertion",
        "trojan_pattern": r"Trojan|comb|insert",
    },
    "s15850-T100": {
        "family": BenchmarkFamily.S15850,
        "description": "Rare-event triggered Trojan",
        "trojan_pattern": r"Trojan|rare|event",
    },
}


class TrustHubDataset(Dataset):
    """PyTorch Geometric Dataset for TrustHub benchmarks.

    Loads trojan-infected and trojan-free circuit graphs with node-level labels
    indicating which gates are part of the trojan circuitry.

    Args:
        root: Root directory for dataset storage.
        benchmark_families: List of benchmark families to include.
        transform: Optional transform to apply to each graph.
        pre_transform: Optional pre-transform to apply before saving.
        download: Whether to download benchmarks if not present.
    """

    def __init__(
        self,
        root: str | Path,
        benchmark_families: list[BenchmarkFamily] | None = None,
        transform: Any = None,
        pre_transform: Any = None,
        download: bool = True,
    ) -> None:
        self._benchmark_families = benchmark_families or list(BenchmarkFamily)
        self._benchmarks: list[TrustHubBenchmark] = []
        self._processed_graphs: list[Data] = []
        self._labels: list[int] = []  # 0 = clean, 1 = trojan

        super().__init__(str(root), transform, pre_transform)

        if download:
            self._setup_benchmarks()

    @property
    def raw_file_names(self) -> list[str]:
        """Return list of raw file names."""
        return ["benchmarks.json"]

    @property
    def processed_file_names(self) -> list[str]:
        """Return list of processed file names."""
        return ["data.pt", "labels.pt", "metadata.json"]

    def _setup_benchmarks(self) -> None:
        """Initialize benchmark configurations."""
        for name, config in TRUSTHUB_BENCHMARKS.items():
            if config["family"] in self._benchmark_families:
                benchmark = TrustHubBenchmark(
                    name=name,
                    family=config["family"],
                    description=config.get("description", ""),
                )
                self._benchmarks.append(benchmark)

    def download(self) -> None:
        """Download TrustHub benchmarks.

        Note: TrustHub requires manual download due to registration.
        This method creates a placeholder structure and instructions.
        """
        raw_dir = Path(self.raw_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)

        instructions = {
            "source": "https://trust-hub.org/#/benchmarks/chip-level-trojan",
            "instructions": [
                "1. Visit https://trust-hub.org and create an account",
                "2. Navigate to Benchmarks -> Chip-Level Trojan",
                "3. Download benchmarks for desired families (AES, RS232, etc.)",
                "4. Extract each benchmark to the 'raw' directory",
                "5. Ensure both trojan (e.g., AES-T100) and golden (e.g., AES) versions exist",
                "6. Re-run the dataset processing",
            ],
            "required_structure": {
                "AES": {
                    "golden": "raw/AES/aes_cipher.v",
                    "trojans": ["raw/AES-T100/", "raw/AES-T200/", "..."],
                },
                "RS232": {
                    "golden": "raw/RS232/uart.v",
                    "trojans": ["raw/RS232-T100/", "raw/RS232-T200/", "..."],
                },
            },
            "benchmarks_with_pairs": list(TRUSTHUB_BENCHMARKS.keys()),
        }

        instructions_path = raw_dir / "DOWNLOAD_INSTRUCTIONS.json"
        with open(instructions_path, "w") as f:
            json.dump(instructions, f, indent=2)

        logger.info(f"Download instructions written to {instructions_path}")
        logger.info("Please download TrustHub benchmarks manually from trust-hub.org")

    def process(self) -> None:
        """Process raw benchmarks into graph format with trojan labels."""
        from backend.file_ingestion import FileCollector
        from backend.syntax_parser import SyntaxParser
        from backend.netlist_synthesizer import NetlistSynthesizer
        from backend.netlist_graph_builder import NetlistGraphBuilder
        from backend.core import History
        from backend.training.labeler import TrojanLabeler

        processed_dir = Path(self.processed_dir)
        processed_dir.mkdir(parents=True, exist_ok=True)

        all_graphs: list[Data] = []
        all_labels: list[int] = []
        metadata: list[dict[str, Any]] = []

        labeler = TrojanLabeler()

        for benchmark in self._benchmarks:
            # Find benchmark files in raw directory
            self._locate_benchmark_files(benchmark)

            if not benchmark.has_both_versions:
                logger.warning(f"Skipping {benchmark.name}: missing trojan or golden version")
                continue

            logger.info(f"Processing {benchmark.name}...")

            # Process trojan version
            try:
                trojan_graph, trojan_node_labels = self._process_single(
                    benchmark.trojan_path,
                    benchmark,
                    is_trojan=True,
                    labeler=labeler,
                )
                if trojan_graph is not None:
                    trojan_graph.y = torch.tensor([1], dtype=torch.long)  # Graph label
                    trojan_graph.node_labels = trojan_node_labels  # Node-level labels
                    trojan_graph.benchmark_name = benchmark.name
                    trojan_graph.is_trojan_version = True
                    all_graphs.append(trojan_graph)
                    all_labels.append(1)
                    metadata.append({
                        "benchmark": benchmark.name,
                        "is_trojan": True,
                        "path": str(benchmark.trojan_path),
                        "trojan_node_count": int(trojan_node_labels.sum().item()),
                        "total_nodes": trojan_graph.num_nodes,
                    })
            except Exception as e:
                logger.error(f"Failed to process trojan version of {benchmark.name}: {e}")

            # Process golden (trojan-free) version
            try:
                golden_graph, _ = self._process_single(
                    benchmark.golden_path,
                    benchmark,
                    is_trojan=False,
                    labeler=labeler,
                )
                if golden_graph is not None:
                    golden_graph.y = torch.tensor([0], dtype=torch.long)  # Graph label
                    golden_graph.node_labels = torch.zeros(golden_graph.num_nodes, dtype=torch.long)
                    golden_graph.benchmark_name = f"{benchmark.name}-golden"
                    golden_graph.is_trojan_version = False
                    all_graphs.append(golden_graph)
                    all_labels.append(0)
                    metadata.append({
                        "benchmark": benchmark.name,
                        "is_trojan": False,
                        "path": str(benchmark.golden_path),
                        "trojan_node_count": 0,
                        "total_nodes": golden_graph.num_nodes,
                    })
            except Exception as e:
                logger.error(f"Failed to process golden version of {benchmark.name}: {e}")

        # Save processed data
        if all_graphs:
            torch.save(all_graphs, processed_dir / "data.pt")
            torch.save(torch.tensor(all_labels), processed_dir / "labels.pt")
            with open(processed_dir / "metadata.json", "w") as f:
                json.dump(metadata, f, indent=2)
            logger.info(f"Saved {len(all_graphs)} processed graphs")
        else:
            logger.warning("No graphs were processed successfully")

    def _locate_benchmark_files(self, benchmark: TrustHubBenchmark) -> None:
        """Locate trojan and golden files for a benchmark."""
        raw_dir = Path(self.raw_dir)

        # Common naming patterns for TrustHub benchmarks
        family_name = benchmark.family.value.upper()

        # Look for trojan version directory
        trojan_patterns = [
            raw_dir / benchmark.name,
            raw_dir / benchmark.name.lower(),
            raw_dir / benchmark.name.replace("-", "_"),
        ]

        for pattern in trojan_patterns:
            if pattern.exists() and pattern.is_dir():
                # Find Verilog files in the directory
                verilog_files = list(pattern.glob("*.v")) + list(pattern.glob("*.sv"))
                if verilog_files:
                    benchmark.trojan_path = pattern
                    break
            elif pattern.with_suffix(".v").exists():
                benchmark.trojan_path = pattern.with_suffix(".v")
                break

        # Look for golden (trojan-free) version
        golden_patterns = [
            raw_dir / family_name,
            raw_dir / family_name.lower(),
            raw_dir / f"{family_name}_golden",
            raw_dir / f"{family_name.lower()}_golden",
            raw_dir / "golden" / family_name,
        ]

        for pattern in golden_patterns:
            if pattern.exists() and pattern.is_dir():
                verilog_files = list(pattern.glob("*.v")) + list(pattern.glob("*.sv"))
                if verilog_files:
                    benchmark.golden_path = pattern
                    break
            elif pattern.with_suffix(".v").exists():
                benchmark.golden_path = pattern.with_suffix(".v")
                break

    def _process_single(
        self,
        path: Path,
        benchmark: TrustHubBenchmark,
        is_trojan: bool,
        labeler: Any,
    ) -> tuple[Data | None, torch.Tensor | None]:
        """Process a single Verilog file/directory into a graph."""
        from backend.file_ingestion import FileCollector
        from backend.syntax_parser import SyntaxParser
        from backend.netlist_synthesizer import NetlistSynthesizer
        from backend.netlist_graph_builder import NetlistGraphBuilder
        from backend.core import History

        history = History()

        # Stage 1: File ingestion
        collector = FileCollector(history)
        ingestion_result = collector.process(path)
        if not ingestion_result.success:
            logger.warning(f"File ingestion failed for {path}")
            return None, None

        # Stage 2: Syntax parsing
        parser = SyntaxParser(history)
        parse_result = parser.process(ingestion_result.data)
        if not parse_result.success:
            logger.warning(f"Parsing failed for {path}")
            return None, None

        # Stage 3: Synthesis
        synthesizer = NetlistSynthesizer(history)
        synth_result = synthesizer.process(parse_result.data)
        if not synth_result.success:
            logger.warning(f"Synthesis failed for {path}")
            return None, None

        # Stage 4: Graph building
        builder = NetlistGraphBuilder(history)
        graph_result = builder.process(synth_result.data)
        if not graph_result.success:
            logger.warning(f"Graph building failed for {path}")
            return None, None

        circuit_graph = graph_result.data
        graph_data = circuit_graph.graph_data

        # Label trojan nodes if this is a trojan version
        if is_trojan:
            node_labels = labeler.label_nodes(
                circuit_graph,
                parse_result.data,
                benchmark,
            )
        else:
            node_labels = torch.zeros(graph_data.num_nodes, dtype=torch.long)

        return graph_data, node_labels

    def len(self) -> int:
        """Return the number of graphs in the dataset."""
        data_path = Path(self.processed_dir) / "data.pt"
        if data_path.exists():
            return len(torch.load(data_path, weights_only=False))
        return 0

    def get(self, idx: int) -> Data:
        """Get a single graph by index."""
        data_path = Path(self.processed_dir) / "data.pt"
        graphs = torch.load(data_path, weights_only=False)
        return graphs[idx]

    def get_metadata(self) -> list[dict[str, Any]]:
        """Load and return dataset metadata."""
        metadata_path = Path(self.processed_dir) / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path) as f:
                return json.load(f)
        return []

    def get_statistics(self) -> dict[str, Any]:
        """Get dataset statistics."""
        metadata = self.get_metadata()

        if not metadata:
            return {"error": "No metadata available"}

        total = len(metadata)
        trojan_count = sum(1 for m in metadata if m["is_trojan"])
        clean_count = total - trojan_count

        trojan_nodes = sum(m["trojan_node_count"] for m in metadata if m["is_trojan"])
        total_nodes = sum(m["total_nodes"] for m in metadata)

        families = {}
        for m in metadata:
            family = m["benchmark"].split("-")[0]
            if family not in families:
                families[family] = {"trojan": 0, "clean": 0}
            if m["is_trojan"]:
                families[family]["trojan"] += 1
            else:
                families[family]["clean"] += 1

        return {
            "total_graphs": total,
            "trojan_graphs": trojan_count,
            "clean_graphs": clean_count,
            "total_nodes": total_nodes,
            "trojan_nodes": trojan_nodes,
            "trojan_node_ratio": trojan_nodes / total_nodes if total_nodes > 0 else 0,
            "families": families,
        }
