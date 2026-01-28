"""VerilogParser for .v files using pyverilog."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from backend.core.exceptions import ParseError
from backend.core.history import History
from backend.syntax_parser.models import (
    Gate,
    ParsedModule,
    Port,
    PortDirection,
    Wire,
)

logger = logging.getLogger(__name__)

STAGE = "syntax_parser"

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


def _normalize_gate_type(gate_type: str) -> str:
    """Normalize a gate type name to its canonical form."""
    lower = gate_type.lower()
    # Check direct match
    if lower in CANONICAL_GATE_MAP:
        return CANONICAL_GATE_MAP[lower]
    # Check prefix match (e.g., AND2, NAND3, DFF_X1)
    for prefix, canonical in CANONICAL_GATE_MAP.items():
        if lower.startswith(prefix):
            return canonical
    return gate_type.upper()


class VerilogParser:
    """Parses standard Verilog (.v) files using the pyverilog library."""

    def __init__(self, history: History) -> None:
        self._history = history

    def parse(self, file_path: Path) -> list[ParsedModule]:
        """Parse a Verilog file and return structured module representations.

        Args:
            file_path: Path to the .v file.

        Returns:
            List of ParsedModule objects extracted from the file.

        Raises:
            ParseError: If the file cannot be parsed.
        """
        try:
            from pyverilog.vparser.parser import parse as pyverilog_parse
        except ImportError as e:
            raise ParseError(
                "pyverilog is not installed. Install it with: pip install pyverilog",
                file_path=str(file_path),
            ) from e

        self._history.info(STAGE, f"Parsing Verilog file with pyverilog: {file_path.name}")

        try:
            ast, _ = pyverilog_parse(
                [str(file_path)],
                preprocess_include=[],
                preprocess_define=[],
            )
        except Exception as e:
            raise ParseError(
                f"Failed to parse Verilog file: {e}",
                file_path=str(file_path),
            ) from e

        modules = self._extract_modules(ast, file_path)

        self._history.info(
            STAGE,
            f"Extracted {len(modules)} module(s) from {file_path.name}",
            data={"module_names": [m.name for m in modules]},
        )

        return modules

    def _extract_modules(self, ast: object, file_path: Path) -> list[ParsedModule]:
        """Walk the pyverilog AST and extract module definitions."""
        from pyverilog.vparser.ast import (
            Description,
            Input,
            Inout,
            Instance,
            InstanceList,
            ModuleDef,
            Output,
            Source,
            Wire as VWire,
            Reg,
            Decl,
            PortArg,
        )

        modules: list[ParsedModule] = []

        if not hasattr(ast, "children"):
            return modules

        for desc in ast.children():
            if not isinstance(desc, Description):
                continue
            for item in desc.children():
                if not isinstance(item, ModuleDef):
                    continue
                module = self._extract_single_module(item, file_path)
                modules.append(module)

        return modules

    def _extract_single_module(self, module_def: object, file_path: Path) -> ParsedModule:
        """Extract a ParsedModule from a pyverilog ModuleDef node."""
        from pyverilog.vparser.ast import (
            Decl,
            Input,
            Inout,
            Instance,
            InstanceList,
            Output,
            PortArg,
            Reg,
            Wire as VWire,
        )

        name = module_def.name  # type: ignore[attr-defined]
        ports: list[Port] = []
        wires: list[Wire] = []
        gates: list[Gate] = []
        submodule_refs: list[str] = []

        for item in module_def.children():  # type: ignore[attr-defined]
            if isinstance(item, Decl):
                for decl_item in item.children():
                    if isinstance(decl_item, Input):
                        width = self._get_width(decl_item)
                        ports.append(Port(name=decl_item.name, direction=PortDirection.INPUT, width=width))
                        wires.append(Wire(name=decl_item.name, width=width, is_input=True))
                    elif isinstance(decl_item, Output):
                        width = self._get_width(decl_item)
                        ports.append(Port(name=decl_item.name, direction=PortDirection.OUTPUT, width=width))
                        wires.append(Wire(name=decl_item.name, width=width, is_output=True))
                    elif isinstance(decl_item, Inout):
                        width = self._get_width(decl_item)
                        ports.append(Port(name=decl_item.name, direction=PortDirection.INOUT, width=width))
                        wires.append(Wire(name=decl_item.name, width=width, is_input=True, is_output=True))
                    elif isinstance(decl_item, VWire):
                        width = self._get_width(decl_item)
                        wires.append(Wire(name=decl_item.name, width=width))
                    elif isinstance(decl_item, Reg):
                        width = self._get_width(decl_item)
                        wires.append(Wire(name=decl_item.name, width=width))

            elif isinstance(item, InstanceList):
                for inst in item.children():
                    if isinstance(inst, Instance):
                        gate_type = item.module  # type: ignore[attr-defined]
                        canonical = _normalize_gate_type(gate_type)
                        input_pins, output_pins = self._extract_instance_pins(inst)

                        gates.append(
                            Gate(
                                instance_name=inst.name,
                                gate_type=gate_type,
                                canonical_type=canonical,
                                input_pins=input_pins,
                                output_pins=output_pins,
                            )
                        )
                        submodule_refs.append(gate_type)

        return ParsedModule(
            name=name,
            gates=gates,
            wires=wires,
            ports=ports,
            submodule_refs=list(set(submodule_refs)),
            source_path=str(file_path),
        )

    def _get_width(self, node: object) -> int:
        """Extract bit width from an AST node."""
        if hasattr(node, "width") and node.width is not None:  # type: ignore[attr-defined]
            width_node = node.width  # type: ignore[attr-defined]
            if hasattr(width_node, "msb") and hasattr(width_node, "lsb"):
                try:
                    msb = int(width_node.msb.value)  # type: ignore[union-attr]
                    lsb = int(width_node.lsb.value)  # type: ignore[union-attr]
                    return abs(msb - lsb) + 1
                except (AttributeError, ValueError, TypeError):
                    pass
        return 1

    def _extract_instance_pins(self, instance: object) -> tuple[list[str], list[str]]:
        """Extract input and output pin connections from a gate instance.

        For gate-level primitives, the first argument is typically the output.
        For module instantiations with named ports, we use naming heuristics.
        """
        from pyverilog.vparser.ast import PortArg

        input_pins: list[str] = []
        output_pins: list[str] = []

        portlist = instance.portlist if hasattr(instance, "portlist") else None  # type: ignore[attr-defined]
        if portlist is None:
            return input_pins, output_pins

        children = list(portlist.children()) if hasattr(portlist, "children") else []

        for i, port_arg in enumerate(children):
            if not isinstance(port_arg, PortArg):
                continue

            pin_name = self._port_arg_to_str(port_arg)

            # Named port connections
            if port_arg.portname and port_arg.portname != "":
                pname_lower = port_arg.portname.lower()
                if any(kw in pname_lower for kw in ("out", "q", "y", "z")):
                    output_pins.append(pin_name)
                else:
                    input_pins.append(pin_name)
            else:
                # Positional: first port is output for primitives
                if i == 0:
                    output_pins.append(pin_name)
                else:
                    input_pins.append(pin_name)

        return input_pins, output_pins

    def _port_arg_to_str(self, port_arg: object) -> str:
        """Convert a PortArg's argument to a string representation."""
        from pyverilog.vparser.ast import Identifier, IntConst, Pointer, Partselect

        arg = port_arg.argname if hasattr(port_arg, "argname") else None  # type: ignore[attr-defined]
        if arg is None:
            return ""
        if isinstance(arg, Identifier):
            return arg.name
        if isinstance(arg, IntConst):
            return str(arg.value)
        if isinstance(arg, Pointer):
            return str(arg.var.name) if hasattr(arg, "var") else str(arg)  # type: ignore[attr-defined]
        if isinstance(arg, Partselect):
            return str(arg.var.name) if hasattr(arg, "var") else str(arg)  # type: ignore[attr-defined]
        return str(arg)
