"""Data models for parsed Verilog/SystemVerilog modules."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PortDirection(str, Enum):
    """Direction of a module port."""

    INPUT = "input"
    OUTPUT = "output"
    INOUT = "inout"


class Port(BaseModel):
    """Module port declaration."""

    name: str
    direction: PortDirection
    width: int = 1
    line_number: int | None = None


class Wire(BaseModel):
    """Wire or register declaration."""

    name: str
    width: int = 1
    array_dimensions: list[int] = Field(default_factory=list)
    is_input: bool = False
    is_output: bool = False
    line_number: int | None = None


class Gate(BaseModel):
    """Gate instance information."""

    instance_name: str
    gate_type: str
    canonical_type: str = ""
    input_pins: list[str] = Field(default_factory=list)
    output_pins: list[str] = Field(default_factory=list)
    line_number: int | None = None


class ParsedModule(BaseModel):
    """Represents a fully parsed Verilog module."""

    name: str
    gates: list[Gate] = Field(default_factory=list)
    wires: list[Wire] = Field(default_factory=list)
    ports: list[Port] = Field(default_factory=list)
    submodule_refs: list[str] = Field(default_factory=list)
    source_path: str = ""


# Mapping from common cell library gate names to canonical types
CANONICAL_GATE_MAP: dict[str, str] = {
    "and": "AND",
    "nand": "NAND",
    "or": "OR",
    "nor": "NOR",
    "xor": "XOR",
    "xnor": "XNOR",
    "not": "NOT",
    "buf": "BUF",
    "inv": "INV",
    "mux": "MUX",
    "dff": "DFF",
    "latch": "LATCH",
}


def normalize_gate_type(gate_type: str) -> str:
    """Normalize a gate type name to its canonical form."""
    lower = gate_type.lower()
    if lower in CANONICAL_GATE_MAP:
        return CANONICAL_GATE_MAP[lower]
    
    for prefix, canonical in CANONICAL_GATE_MAP.items():
        if lower.startswith(prefix):
            return canonical
    
    return gate_type.upper()
