"""SystemVerilogParser for .sv files using pyslang."""

from __future__ import annotations

import logging
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
from backend.syntax_parser.verilog_parser import _normalize_gate_type

logger = logging.getLogger(__name__)

STAGE = "syntax_parser"


class SystemVerilogParser:
    """Parses SystemVerilog (.sv) files using the pyslang library."""

    def __init__(self, history: History) -> None:
        self._history = history

    def parse(self, file_path: Path) -> list[ParsedModule]:
        """Parse a SystemVerilog file and return structured module representations.

        Args:
            file_path: Path to the .sv file.

        Returns:
            List of ParsedModule objects extracted from the file.

        Raises:
            ParseError: If the file cannot be parsed.
        """
        try:
            import pyslang
        except ImportError as e:
            raise ParseError(
                "pyslang is not installed. Install it with: pip install pyslang",
                file_path=str(file_path),
            ) from e

        self._history.info(STAGE, f"Parsing SystemVerilog file with pyslang: {file_path.name}")

        try:
            tree = pyslang.SyntaxTree.fromFile(str(file_path))
            compilation = pyslang.Compilation()
            compilation.addSyntaxTree(tree)
        except Exception as e:
            raise ParseError(
                f"Failed to parse SystemVerilog file: {e}",
                file_path=str(file_path),
            ) from e

        # Report diagnostics
        diagnostics = compilation.getAllDiagnostics()
        for diag in diagnostics:
            diag_str = str(diag)
            if "error" in diag_str.lower():
                self._history.error(STAGE, f"pyslang error: {diag_str}")
            else:
                self._history.warning(STAGE, f"pyslang diagnostic: {diag_str}")

        modules = self._extract_modules(compilation, file_path)

        self._history.info(
            STAGE,
            f"Extracted {len(modules)} module(s) from {file_path.name}",
            data={"module_names": [m.name for m in modules]},
        )

        return modules

    def _extract_modules(self, compilation: object, file_path: Path) -> list[ParsedModule]:
        """Extract modules from a pyslang compilation."""
        import pyslang

        modules: list[ParsedModule] = []
        root = compilation.getRoot()  # type: ignore[attr-defined]

        for member in root.members:  # type: ignore[attr-defined]
            if member.kind == pyslang.SymbolKind.Instance:
                body = member.body  # type: ignore[attr-defined]
                if body.kind == pyslang.SymbolKind.InstanceBody:
                    module = self._extract_single_module(body, file_path)
                    modules.append(module)

        return modules

    def _extract_single_module(self, body: object, file_path: Path) -> ParsedModule:
        """Extract a ParsedModule from a pyslang instance body."""
        import pyslang

        name = body.name  # type: ignore[attr-defined]
        ports: list[Port] = []
        wires: list[Wire] = []
        gates: list[Gate] = []
        submodule_refs: list[str] = []

        for member in body.members:  # type: ignore[attr-defined]
            kind = member.kind  # type: ignore[attr-defined]

            if kind == pyslang.SymbolKind.Port:
                direction = self._map_direction(member)
                width = self._get_type_width(member)
                lineno = self._get_line_number(member)
                ports.append(Port(name=member.name, direction=direction, width=width, line_number=lineno))
                wires.append(Wire(
                    name=member.name,
                    width=width,
                    is_input=(direction == PortDirection.INPUT),
                    is_output=(direction == PortDirection.OUTPUT),
                    line_number=lineno,
                ))

            elif kind == pyslang.SymbolKind.Net:
                width = self._get_type_width(member)
                lineno = self._get_line_number(member)
                wires.append(Wire(name=member.name, width=width, line_number=lineno))

            elif kind == pyslang.SymbolKind.Variable:
                width = self._get_type_width(member)
                lineno = self._get_line_number(member)
                wires.append(Wire(name=member.name, width=width, line_number=lineno))

            elif kind == pyslang.SymbolKind.Instance:
                inst_body = member.body  # type: ignore[attr-defined]
                gate_type = inst_body.name if hasattr(inst_body, "name") else str(kind)
                canonical = _normalize_gate_type(gate_type)
                inst_name = member.name  # type: ignore[attr-defined]

                input_pins, output_pins = self._extract_instance_connections(member)

                gates.append(Gate(
                    instance_name=inst_name,
                    gate_type=gate_type,
                    canonical_type=canonical,
                    input_pins=input_pins,
                    output_pins=output_pins,
                    line_number=self._get_line_number(member),
                ))
                submodule_refs.append(gate_type)

        return ParsedModule(
            name=name,
            gates=gates,
            wires=wires,
            ports=ports,
            submodule_refs=list(set(submodule_refs)),
            source_path=str(file_path),
        )

    def _map_direction(self, port: object) -> PortDirection:
        """Map pyslang port direction to PortDirection."""
        import pyslang

        direction = port.direction  # type: ignore[attr-defined]
        if direction == pyslang.ArgumentDirection.In:
            return PortDirection.INPUT
        elif direction == pyslang.ArgumentDirection.Out:
            return PortDirection.OUTPUT
        elif direction == pyslang.ArgumentDirection.InOut:
            return PortDirection.INOUT
        return PortDirection.INPUT

    def _get_line_number(self, member: object) -> int | None:
        """Extract the source line number from a pyslang symbol."""
        try:
            loc = member.location  # type: ignore[attr-defined]
            # pyslang SourceLocation may expose line directly or need decoding
            if hasattr(loc, "line"):
                return int(loc.line)
        except Exception:
            pass
        return None

    def _get_type_width(self, member: object) -> int:
        """Extract bit width from a pyslang symbol's type."""
        try:
            type_obj = member.getType()  # type: ignore[attr-defined]
            if hasattr(type_obj, "getBitVectorRange"):
                range_obj = type_obj.getBitVectorRange()
                return range_obj.width  # type: ignore[attr-defined]
            if hasattr(type_obj, "bitWidth"):
                return type_obj.bitWidth  # type: ignore[attr-defined]
        except Exception:
            pass
        return 1

    def _extract_instance_connections(self, instance: object) -> tuple[list[str], list[str]]:
        """Extract input and output pin connections from an instance."""
        import pyslang

        input_pins: list[str] = []
        output_pins: list[str] = []

        try:
            body = instance.body  # type: ignore[attr-defined]
            for port_member in body.members:  # type: ignore[attr-defined]
                if port_member.kind != pyslang.SymbolKind.Port:
                    continue
                port_name = port_member.name  # type: ignore[attr-defined]
                direction = port_member.direction  # type: ignore[attr-defined]
                if direction == pyslang.ArgumentDirection.Out:
                    output_pins.append(port_name)
                else:
                    input_pins.append(port_name)
        except Exception:
            pass

        return input_pins, output_pins
