"""Netlist synthesizer module using Yosys for validation and elaboration."""

from trojan_detector.backend.netlist_synthesizer.models import CellStatistics, SynthesisResult
from trojan_detector.backend.netlist_synthesizer.synthesizer import NetlistSynthesizer

__all__ = ["NetlistSynthesizer", "SynthesisResult", "CellStatistics"]
