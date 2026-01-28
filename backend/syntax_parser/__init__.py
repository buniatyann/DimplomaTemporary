"""Syntax parser module for Verilog and SystemVerilog files."""

from trojan_detector.backend.syntax_parser.models import Gate, ParsedModule, Port, Wire
from trojan_detector.backend.syntax_parser.parser import SyntaxParser

__all__ = ["SyntaxParser", "ParsedModule", "Gate", "Wire", "Port"]
