"""Unified Verilog/SystemVerilog parser using pyslang (Slang C++ backend).

Replaces both the old pyverilog-based VerilogParser and the previous
pyslang-based SystemVerilogParser with a single implementation that
handles .v, .vh, and .sv files through pyslang's IEEE 1800-2017
compliant parser.
"""

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
    normalize_gate_type,
)

logger = logging.getLogger(__name__)

STAGE = "syntax_parser"


class SystemVerilogParser:
    """Parses Verilog (.v) and SystemVerilog (.sv) files using pyslang.

    Pyslang is a Python binding for Slang, a fully IEEE 1800-2017 compliant
    parser built in C++. It handles all Verilog/SystemVerilog constructs
    that pyverilog's LALR parser cannot, and provides exact source locations
    for every symbol.
    """

    def __init__(self, history: History) -> None:
        self._history = history

    def parse(self, file_path: Path) -> list[ParsedModule]:
        """Parse a Verilog or SystemVerilog file.

        Args:
            file_path: Path to the .v or .sv file.

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

        self._history.info(STAGE, f"Parsing with pyslang: {file_path.name}")

        try:
            tree = pyslang.SyntaxTree.fromFile(str(file_path))
            compilation = pyslang.Compilation()
            compilation.addSyntaxTree(tree)
        except Exception as e:
            raise ParseError(
                f"Failed to parse file: {e}",
                file_path=str(file_path),
            ) from e

        # Report diagnostics
        diagnostics = compilation.getAllDiagnostics()
        for diag in diagnostics:
            diag_str = str(diag)
            if "error" in diag_str.lower():
                self._history.warning(STAGE, f"pyslang diagnostic: {diag_str}")

        sm = tree.sourceManager
        modules = self._extract_modules(compilation, file_path, sm)

        self._history.info(
            STAGE,
            f"Extracted {len(modules)} module(s) from {file_path.name}",
            data={"module_names": [m.name for m in modules]},
        )

        return modules

    def _extract_modules(
        self, compilation: object, file_path: Path, sm: object,
    ) -> list[ParsedModule]:
        """Extract modules from a pyslang compilation."""
        import pyslang

        modules: list[ParsedModule] = []
        root = compilation.getRoot()

        for inst in root.topInstances:
            if inst.kind == pyslang.SymbolKind.Instance:
                body = inst.body
                if body.kind == pyslang.SymbolKind.InstanceBody:
                    module = self._extract_single_module(body, file_path, sm)
                    modules.append(module)

        return modules

    def _extract_single_module(
        self, body: object, file_path: Path, sm: object,
    ) -> ParsedModule:
        """Extract a ParsedModule from a pyslang instance body."""
        import pyslang

        name = body.name
        ports: list[Port] = []
        wires: list[Wire] = []
        gates: list[Gate] = []
        submodule_refs: list[str] = []

        # Collect all symbols via visitor
        members: list = []

        def visitor(sym: object) -> object:
            members.append(sym)
            return pyslang.VisitAction.Advance

        body.visit(visitor)

        # Track which names we've added as ports to avoid wire duplicates
        port_names: set[str] = set()

        # Process ports from portList (reliable direction info)
        for port in body.portList:
            if port.kind != pyslang.SymbolKind.Port:
                continue
            direction = self._map_direction(port)
            width = self._get_width_from_body(body, port.name)
            lineno = self._get_line_number(port, sm)
            ports.append(Port(
                name=port.name,
                direction=direction,
                width=width,
                line_number=lineno,
            ))
            wires.append(Wire(
                name=port.name,
                width=width,
                is_input=(direction == PortDirection.INPUT),
                is_output=(direction == PortDirection.OUTPUT),
                line_number=lineno,
            ))
            port_names.add(port.name)

        # Process remaining members
        for member in members:
            kind = member.kind

            if kind == pyslang.SymbolKind.Net:
                if member.name in port_names:
                    continue
                width = self._get_width(member)
                lineno = self._get_line_number(member, sm)
                wires.append(Wire(
                    name=member.name,
                    width=width,
                    line_number=lineno,
                ))

            elif kind == pyslang.SymbolKind.Variable:
                if member.name in port_names:
                    continue
                width = self._get_width(member)
                lineno = self._get_line_number(member, sm)
                wires.append(Wire(
                    name=member.name,
                    width=width,
                    line_number=lineno,
                ))

            elif kind == pyslang.SymbolKind.Instance:
                inst_body = member.body
                gate_type = inst_body.name if hasattr(inst_body, "name") else str(kind)
                canonical = normalize_gate_type(gate_type)
                inst_name = member.name

                input_pins, output_pins = self._extract_instance_connections(member)

                gates.append(Gate(
                    instance_name=inst_name,
                    gate_type=gate_type,
                    canonical_type=canonical,
                    input_pins=input_pins,
                    output_pins=output_pins,
                    line_number=self._get_line_number(member, sm),
                ))
                submodule_refs.append(gate_type)

            elif kind == pyslang.SymbolKind.PrimitiveInstance:
                prim_type = member.primitiveType
                gate_type = prim_type.name if hasattr(prim_type, "name") else str(prim_type)
                canonical = normalize_gate_type(gate_type)
                inst_name = member.name

                input_pins, output_pins = self._extract_primitive_connections(member)

                gates.append(Gate(
                    instance_name=inst_name,
                    gate_type=gate_type,
                    canonical_type=canonical,
                    input_pins=input_pins,
                    output_pins=output_pins,
                    line_number=self._get_line_number(member, sm),
                ))

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

        direction = port.direction
        if direction == pyslang.ArgumentDirection.In:
            return PortDirection.INPUT
        elif direction == pyslang.ArgumentDirection.Out:
            return PortDirection.OUTPUT
        elif direction == pyslang.ArgumentDirection.InOut:
            return PortDirection.INOUT
        return PortDirection.INPUT

    def _get_line_number(self, member: object, sm: object) -> int | None:
        """Extract the source line number from a pyslang symbol."""
        try:
            loc = member.location
            return sm.getLineNumber(loc)
        except Exception:
            return None

    def _get_width(self, member: object) -> int:
        """Extract bit width from a pyslang symbol's type property."""
        try:
            tp = member.type
            if hasattr(tp, "bitWidth"):
                return tp.bitWidth
        except Exception:
            pass
        return 1

    def _get_width_from_body(self, body: object, port_name: str) -> int:
        """Get width of a port by looking up the underlying net/variable."""
        try:
            inner = body.find(port_name)
            if inner is not None:
                return self._get_width(inner)
        except Exception:
            pass
        return 1

    def _extract_instance_connections(
        self, instance: object,
    ) -> tuple[list[str], list[str]]:
        """Extract input and output pin connections from a module instance."""
        import pyslang

        input_pins: list[str] = []
        output_pins: list[str] = []

        try:
            inst_body = instance.body
            for port_member in inst_body.portList:
                if port_member.kind != pyslang.SymbolKind.Port:
                    continue
                port_name = port_member.name
                direction = port_member.direction
                if direction == pyslang.ArgumentDirection.Out:
                    output_pins.append(port_name)
                else:
                    input_pins.append(port_name)
        except Exception:
            pass

        return input_pins, output_pins

    def _extract_primitive_connections(
        self, primitive: object,
    ) -> tuple[list[str], list[str]]:
        """Extract input and output connections from a gate primitive.

        For Verilog gate primitives (and, or, nand, etc.), the first
        connection is the output, the rest are inputs.
        """
        import pyslang

        input_pins: list[str] = []
        output_pins: list[str] = []

        try:
            conns = primitive.portConnections
            for i, conn in enumerate(conns):
                pin_name = self._expression_to_str(conn)
                if i == 0:
                    output_pins.append(pin_name)
                else:
                    input_pins.append(pin_name)
        except Exception:
            pass

        return input_pins, output_pins

    def _expression_to_str(self, expr: object) -> str:
        """Convert a pyslang expression to a signal name string."""
        import pyslang

        try:
            if expr.kind == pyslang.ExpressionKind.NamedValue:
                sym = expr.getSymbolReference()
                if sym:
                    return sym.name
            elif expr.kind == pyslang.ExpressionKind.Assignment:
                # Assignment expressions: use the left side
                return self._expression_to_str(expr.left)
            elif expr.kind == pyslang.ExpressionKind.EmptyArgument:
                return ""
        except Exception:
            pass
        return str(expr)
