#!/usr/bin/env python3
"""Generate large-scale TrustHub-style benchmarks for GNN training.

This script generates 200+ paired trojan/golden Verilog files with
realistic circuit structures ranging from small to very large (200k+ lines).

Usage:
    python -m backend.training.generate_large_benchmarks --count 200
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Trojan patterns to inject
TROJAN_PATTERNS = [
    "Trojan", "Tj_", "trigger", "payload", "backdoor", "leak", "mal_", "ht_"
]

# Circuit component templates
REGISTER_TEMPLATE = """
    // {comment}
    reg [{width}:0] {name};
    always @(posedge clk or posedge rst) begin
        if (rst) {name} <= {init};
        else {name} <= {next_val};
    end
"""

WIRE_TEMPLATE = """    wire [{width}:0] {name};
    assign {name} = {expr};
"""

COUNTER_TEMPLATE = """
    // {comment}
    reg [{width}:0] {name};
    always @(posedge clk or posedge rst) begin
        if (rst) {name} <= {width}'d0;
        else if ({enable}) {name} <= {name} + 1;
    end
"""

FSM_TEMPLATE = """
    // {comment}
    reg [{state_bits}:0] {name}_state;
    localparam {name}_IDLE = {state_bits}'d0;
    localparam {name}_ACTIVE = {state_bits}'d1;
    localparam {name}_DONE = {state_bits}'d2;

    always @(posedge clk or posedge rst) begin
        if (rst) {name}_state <= {name}_IDLE;
        else begin
            case ({name}_state)
                {name}_IDLE: if ({start}) {name}_state <= {name}_ACTIVE;
                {name}_ACTIVE: if ({done_cond}) {name}_state <= {name}_DONE;
                {name}_DONE: {name}_state <= {name}_IDLE;
                default: {name}_state <= {name}_IDLE;
            endcase
        end
    end
"""

MEMORY_TEMPLATE = """
    // {comment}
    reg [{data_width}:0] {name} [0:{depth}];

    always @(posedge clk) begin
        if ({wr_en}) {name}[{addr}] <= {data_in};
    end

    assign {data_out} = {name}[{addr}];
"""

TROJAN_TRIGGER_TEMPLATE = """
    // Trojan trigger logic
    reg [{width}:0] {name}_counter;
    wire {name}_trigger = ({trigger_cond});
    reg {name}_armed;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            {name}_counter <= {width}'d0;
            {name}_armed <= 1'b0;
        end else begin
            if ({name}_trigger) begin
                {name}_counter <= {name}_counter + 1;
                if ({name}_counter >= {threshold}) {name}_armed <= 1'b1;
            end
        end
    end
"""

TROJAN_PAYLOAD_TEMPLATE = """
    // Trojan payload
    reg [{width}:0] {name}_payload;
    reg {name}_active;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            {name}_payload <= {width}'d0;
            {name}_active <= 1'b0;
        end else if ({trigger}) begin
            {name}_active <= 1'b1;
            {name}_payload <= {leak_data};
        end
    end
"""


def generate_signal_name(prefix: str, idx: int, is_trojan: bool = False) -> str:
    """Generate a signal name, optionally with trojan pattern."""
    if is_trojan and random.random() < 0.7:
        trojan_prefix = random.choice(TROJAN_PATTERNS)
        return f"{trojan_prefix}_{prefix}_{idx}"
    return f"{prefix}_{idx}"


def generate_expression(signals: list[str], width: int) -> str:
    """Generate a random combinational expression."""
    if not signals or random.random() < 0.1:
        return f"{width}'d{random.randint(0, 2**min(width, 16)-1)}"

    ops = ["^", "&", "|", "+", "-"]
    if len(signals) == 1:
        return signals[0]

    s1 = random.choice(signals)
    s2 = random.choice(signals)
    op = random.choice(ops)

    if random.random() < 0.3:
        return f"({s1} {op} {s2})"
    return f"{s1} {op} {s2}"


def generate_module(
    name: str,
    num_inputs: int,
    num_outputs: int,
    num_registers: int,
    num_wires: int,
    num_memories: int,
    num_fsms: int,
    is_trojan: bool,
    complexity: str = "medium",
) -> str:
    """Generate a Verilog module with specified complexity."""

    lines = []
    lines.append(f"// {'Trojan-infected' if is_trojan else 'Golden'} {name} module")
    lines.append(f"// Complexity: {complexity}")
    lines.append("")

    # Module declaration
    input_ports = ["clk", "rst"]
    output_ports = []

    # Generate input/output declarations
    input_widths = {}
    output_widths = {}

    for i in range(num_inputs):
        width = random.choice([1, 8, 16, 32, 64, 128])
        port_name = f"data_in_{i}"
        input_ports.append(port_name)
        input_widths[port_name] = width

    for i in range(num_outputs):
        width = random.choice([1, 8, 16, 32, 64, 128])
        port_name = f"data_out_{i}"
        output_ports.append(port_name)
        output_widths[port_name] = width

    # Module header
    all_ports = input_ports + output_ports
    lines.append(f"module {name}(")
    lines.append("    " + ",\n    ".join(all_ports))
    lines.append(");")
    lines.append("")

    # Port declarations
    lines.append("    input clk;")
    lines.append("    input rst;")
    for port in input_ports[2:]:
        w = input_widths[port]
        if w > 1:
            lines.append(f"    input [{w-1}:0] {port};")
        else:
            lines.append(f"    input {port};")

    for port in output_ports:
        w = output_widths[port]
        if w > 1:
            lines.append(f"    output reg [{w-1}:0] {port};")
        else:
            lines.append(f"    output reg {port};")

    lines.append("")

    # Track all signals for expression generation
    all_signals = list(input_ports[2:])
    register_signals = []
    wire_signals = []

    # Generate registers
    for i in range(num_registers):
        width = random.choice([8, 16, 32, 64])
        reg_name = generate_signal_name("reg", i, is_trojan and random.random() < 0.1)
        register_signals.append(reg_name)
        all_signals.append(reg_name)

        expr = generate_expression(all_signals[:-1] if all_signals[:-1] else ["1'b0"], width)
        enable = random.choice(all_signals) if all_signals else "1'b1"

        lines.append(f"    reg [{width-1}:0] {reg_name};")
        lines.append(f"    always @(posedge clk or posedge rst) begin")
        lines.append(f"        if (rst) {reg_name} <= {width}'d0;")
        lines.append(f"        else if ({enable}[0]) {reg_name} <= {expr};")
        lines.append(f"    end")
        lines.append("")

    # Generate wires
    for i in range(num_wires):
        width = random.choice([1, 8, 16, 32])
        wire_name = generate_signal_name("wire", i, is_trojan and random.random() < 0.05)
        wire_signals.append(wire_name)
        all_signals.append(wire_name)

        expr = generate_expression(all_signals[:-1] if all_signals[:-1] else ["1'b0"], width)

        if width > 1:
            lines.append(f"    wire [{width-1}:0] {wire_name};")
        else:
            lines.append(f"    wire {wire_name};")
        lines.append(f"    assign {wire_name} = {expr};")
        lines.append("")

    # Generate memories
    for i in range(num_memories):
        data_width = random.choice([8, 16, 32])
        depth = random.choice([16, 32, 64, 128, 256])
        addr_bits = (depth - 1).bit_length()
        mem_name = generate_signal_name("mem", i, is_trojan and random.random() < 0.1)

        lines.append(f"    // Memory block {i}")
        lines.append(f"    reg [{data_width-1}:0] {mem_name} [0:{depth-1}];")
        lines.append(f"    reg [{addr_bits-1}:0] {mem_name}_addr;")
        lines.append(f"    reg {mem_name}_wr_en;")
        lines.append(f"    wire [{data_width-1}:0] {mem_name}_rd_data;")
        lines.append(f"    assign {mem_name}_rd_data = {mem_name}[{mem_name}_addr];")
        lines.append(f"    always @(posedge clk) begin")
        lines.append(f"        if ({mem_name}_wr_en) {mem_name}[{mem_name}_addr] <= data_in_0[{data_width-1}:0];")
        lines.append(f"    end")
        lines.append("")

        all_signals.extend([f"{mem_name}_addr", f"{mem_name}_rd_data"])

    # Generate FSMs
    for i in range(num_fsms):
        state_bits = random.choice([2, 3, 4])
        num_states = 2 ** state_bits
        fsm_name = generate_signal_name("fsm", i, is_trojan and random.random() < 0.15)

        lines.append(f"    // FSM {i}")
        lines.append(f"    reg [{state_bits-1}:0] {fsm_name}_state;")
        for s in range(min(num_states, 8)):
            lines.append(f"    localparam {fsm_name}_S{s} = {state_bits}'d{s};")

        lines.append(f"    always @(posedge clk or posedge rst) begin")
        lines.append(f"        if (rst) {fsm_name}_state <= {fsm_name}_S0;")
        lines.append(f"        else begin")
        lines.append(f"            case ({fsm_name}_state)")

        for s in range(min(num_states, 8)):
            next_state = (s + 1) % min(num_states, 8)
            cond = random.choice(all_signals) if all_signals else "1'b1"
            lines.append(f"                {fsm_name}_S{s}: if ({cond}[0]) {fsm_name}_state <= {fsm_name}_S{next_state};")

        lines.append(f"                default: {fsm_name}_state <= {fsm_name}_S0;")
        lines.append(f"            endcase")
        lines.append(f"        end")
        lines.append(f"    end")
        lines.append("")

        all_signals.append(f"{fsm_name}_state")

    # Add trojan logic if this is a trojan module
    if is_trojan:
        num_trojans = random.randint(1, 3)
        for t in range(num_trojans):
            trojan_type = random.choice(["counter", "pattern", "sequence", "timer"])

            if trojan_type == "counter":
                width = random.choice([16, 24, 32])
                threshold = random.randint(1000, 1000000)
                lines.append(f"    // Trojan {t}: Counter-based trigger")
                lines.append(f"    reg [{width-1}:0] Trojan_counter_{t};")
                lines.append(f"    wire Trojan_trigger_{t} = (Trojan_counter_{t} >= {width}'d{threshold});")
                lines.append(f"    reg Trojan_active_{t};")
                lines.append(f"    always @(posedge clk or posedge rst) begin")
                lines.append(f"        if (rst) begin")
                lines.append(f"            Trojan_counter_{t} <= {width}'d0;")
                lines.append(f"            Trojan_active_{t} <= 1'b0;")
                lines.append(f"        end else begin")
                lines.append(f"            Trojan_counter_{t} <= Trojan_counter_{t} + 1;")
                lines.append(f"            if (Trojan_trigger_{t}) Trojan_active_{t} <= 1'b1;")
                lines.append(f"        end")
                lines.append(f"    end")
                lines.append("")

            elif trojan_type == "pattern":
                pattern = hex(random.randint(0, 0xFFFFFFFF))[2:].upper()
                width = 32
                lines.append(f"    // Trojan {t}: Pattern-matching trigger")
                lines.append(f"    wire Tj_pattern_match_{t} = (data_in_0[31:0] == 32'h{pattern});")
                lines.append(f"    reg [7:0] Tj_match_count_{t};")
                lines.append(f"    reg Tj_armed_{t};")
                lines.append(f"    always @(posedge clk or posedge rst) begin")
                lines.append(f"        if (rst) begin")
                lines.append(f"            Tj_match_count_{t} <= 8'd0;")
                lines.append(f"            Tj_armed_{t} <= 1'b0;")
                lines.append(f"        end else if (Tj_pattern_match_{t}) begin")
                lines.append(f"            Tj_match_count_{t} <= Tj_match_count_{t} + 1;")
                lines.append(f"            if (Tj_match_count_{t} >= 8'd10) Tj_armed_{t} <= 1'b1;")
                lines.append(f"        end")
                lines.append(f"    end")
                lines.append("")

            elif trojan_type == "sequence":
                lines.append(f"    // Trojan {t}: Sequence detector")
                lines.append(f"    reg [63:0] ht_shift_reg_{t};")
                lines.append(f"    wire ht_sequence_match_{t} = (ht_shift_reg_{t} == 64'hDEADBEEFCAFEBABE);")
                lines.append(f"    reg ht_payload_enable_{t};")
                lines.append(f"    always @(posedge clk or posedge rst) begin")
                lines.append(f"        if (rst) begin")
                lines.append(f"            ht_shift_reg_{t} <= 64'd0;")
                lines.append(f"            ht_payload_enable_{t} <= 1'b0;")
                lines.append(f"        end else begin")
                lines.append(f"            ht_shift_reg_{t} <= {{ht_shift_reg_{t}[55:0], data_in_0[7:0]}};")
                lines.append(f"            if (ht_sequence_match_{t}) ht_payload_enable_{t} <= 1'b1;")
                lines.append(f"        end")
                lines.append(f"    end")
                lines.append("")

            elif trojan_type == "timer":
                lines.append(f"    // Trojan {t}: Time-bomb trigger")
                lines.append(f"    reg [47:0] mal_timer_{t};")
                lines.append(f"    wire mal_timeout_{t} = (mal_timer_{t} >= 48'h0000FFFFFFFF);")
                lines.append(f"    reg [31:0] mal_leak_data_{t};")
                lines.append(f"    always @(posedge clk or posedge rst) begin")
                lines.append(f"        if (rst) begin")
                lines.append(f"            mal_timer_{t} <= 48'd0;")
                lines.append(f"            mal_leak_data_{t} <= 32'd0;")
                lines.append(f"        end else begin")
                lines.append(f"            mal_timer_{t} <= mal_timer_{t} + 1;")
                lines.append(f"            if (mal_timeout_{t}) mal_leak_data_{t} <= data_in_0[31:0];")
                lines.append(f"        end")
                lines.append(f"    end")
                lines.append("")

    # Output assignments
    lines.append("    // Output logic")
    for i, port in enumerate(output_ports):
        w = output_widths[port]
        if register_signals:
            src = random.choice(register_signals)
            lines.append(f"    always @(posedge clk) begin")
            lines.append(f"        {port} <= {src}[{w-1}:0];")
            lines.append(f"    end")
        else:
            lines.append(f"    always @(posedge clk) begin")
            lines.append(f"        {port} <= {w}'d0;")
            lines.append(f"    end")

    lines.append("")
    lines.append("endmodule")

    return "\n".join(lines)


def generate_large_module(
    name: str,
    target_lines: int,
    is_trojan: bool,
) -> str:
    """Generate a large module with approximately target_lines of code."""

    # Estimate lines per component
    lines_per_register = 6
    lines_per_wire = 3
    lines_per_memory = 10
    lines_per_fsm = 20
    base_lines = 50

    # Calculate number of components needed
    available_lines = target_lines - base_lines

    # Distribute lines among components
    num_registers = available_lines // (4 * lines_per_register)
    num_wires = available_lines // (4 * lines_per_wire)
    num_memories = min(50, available_lines // (8 * lines_per_memory))
    num_fsms = min(30, available_lines // (8 * lines_per_fsm))

    # Scale up for very large modules
    if target_lines > 100000:
        num_registers = min(5000, num_registers * 2)
        num_wires = min(3000, num_wires * 2)
        num_memories = min(100, num_memories * 2)
        num_fsms = min(50, num_fsms * 2)

    complexity = "small" if target_lines < 1000 else "medium" if target_lines < 50000 else "large" if target_lines < 200000 else "very_large"

    return generate_module(
        name=name,
        num_inputs=random.randint(4, 16),
        num_outputs=random.randint(4, 16),
        num_registers=num_registers,
        num_wires=num_wires,
        num_memories=num_memories,
        num_fsms=num_fsms,
        is_trojan=is_trojan,
        complexity=complexity,
    )


def generate_hierarchical_design(
    name: str,
    target_lines: int,
    is_trojan: bool,
    num_submodules: int = 5,
) -> str:
    """Generate a hierarchical design with multiple submodules."""

    lines = []
    lines.append(f"// {'Trojan-infected' if is_trojan else 'Golden'} hierarchical design: {name}")
    lines.append(f"// Target size: ~{target_lines} lines")
    lines.append("")

    # Generate submodules
    lines_per_submodule = target_lines // (num_submodules + 1)
    submodule_names = []

    for i in range(num_submodules):
        sub_name = f"{name}_sub_{i}"
        submodule_names.append(sub_name)
        # Only some submodules have trojans in infected designs
        sub_is_trojan = is_trojan and (i < num_submodules // 2)
        sub_module = generate_large_module(sub_name, lines_per_submodule, sub_is_trojan)
        lines.append(sub_module)
        lines.append("")

    # Generate top module that instantiates submodules
    lines.append(f"// Top module")
    lines.append(f"module {name}_top(")
    lines.append("    input clk,")
    lines.append("    input rst,")
    lines.append("    input [127:0] data_in,")
    lines.append("    output reg [127:0] data_out")
    lines.append(");")
    lines.append("")

    # Interconnect wires
    for i, sub_name in enumerate(submodule_names):
        lines.append(f"    wire [127:0] {sub_name}_out;")

    lines.append("")

    # Instantiate submodules
    for i, sub_name in enumerate(submodule_names):
        prev_out = "data_in" if i == 0 else f"{submodule_names[i-1]}_out"
        lines.append(f"    {sub_name} u_{sub_name} (")
        lines.append(f"        .clk(clk),")
        lines.append(f"        .rst(rst),")
        lines.append(f"        .data_in_0({prev_out}),")
        lines.append(f"        .data_out_0({sub_name}_out)")
        lines.append(f"    );")
        lines.append("")

    # Output assignment
    last_out = f"{submodule_names[-1]}_out" if submodule_names else "128'd0"
    lines.append(f"    always @(posedge clk) data_out <= {last_out};")
    lines.append("")
    lines.append("endmodule")

    return "\n".join(lines)


# Benchmark configurations with varying sizes
BENCHMARK_CONFIGS = [
    # Small benchmarks (100-1000 lines)
    {"prefix": "aes_small", "lines": 500, "count": 20},
    {"prefix": "uart_small", "lines": 300, "count": 20},
    {"prefix": "spi_small", "lines": 400, "count": 20},
    {"prefix": "i2c_small", "lines": 600, "count": 20},
    {"prefix": "fifo_small", "lines": 200, "count": 20},

    # Medium benchmarks (1000-10000 lines)
    {"prefix": "aes_medium", "lines": 5000, "count": 15},
    {"prefix": "rsa_medium", "lines": 8000, "count": 15},
    {"prefix": "sha_medium", "lines": 6000, "count": 15},
    {"prefix": "dma_medium", "lines": 4000, "count": 15},
    {"prefix": "pcie_medium", "lines": 10000, "count": 10},

    # Large benchmarks (10000-100000 lines)
    {"prefix": "soc_large", "lines": 50000, "count": 10},
    {"prefix": "cpu_large", "lines": 80000, "count": 5},
    {"prefix": "gpu_large", "lines": 100000, "count": 5},

    # Very large benchmarks (200000+ lines)
    {"prefix": "asic_xlarge", "lines": 200000, "count": 5},
    {"prefix": "fpga_xlarge", "lines": 250000, "count": 3},
    {"prefix": "soc_xlarge", "lines": 300000, "count": 2},
]


def generate_benchmarks(output_dir: Path, total_count: int = 200) -> None:
    """Generate benchmark files."""

    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    config_idx = 0

    while generated < total_count:
        config = BENCHMARK_CONFIGS[config_idx % len(BENCHMARK_CONFIGS)]

        for i in range(min(config["count"], total_count - generated)):
            bench_num = generated + i

            # Generate trojan version
            trojan_name = f"{config['prefix']}_T{bench_num:03d}"
            trojan_dir = raw_dir / trojan_name
            trojan_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Generating {trojan_name} (~{config['lines']} lines)...")

            if config["lines"] > 50000:
                # Use hierarchical design for large modules
                trojan_code = generate_hierarchical_design(
                    trojan_name, config["lines"], is_trojan=True
                )
            else:
                trojan_code = generate_large_module(
                    trojan_name, config["lines"], is_trojan=True
                )

            trojan_file = trojan_dir / f"{trojan_name.lower()}.v"
            trojan_file.write_text(trojan_code)

            # Generate golden version
            golden_name = f"{config['prefix']}_golden_{bench_num:03d}"
            golden_dir = raw_dir / golden_name
            golden_dir.mkdir(parents=True, exist_ok=True)

            if config["lines"] > 50000:
                golden_code = generate_hierarchical_design(
                    golden_name, config["lines"], is_trojan=False
                )
            else:
                golden_code = generate_large_module(
                    golden_name, config["lines"], is_trojan=False
                )

            golden_file = golden_dir / f"{golden_name.lower()}.v"
            golden_file.write_text(golden_code)

            generated += 1

            if generated >= total_count:
                break

        config_idx += 1

    logger.info(f"Generated {generated} trojan/golden pairs")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate large-scale TrustHub-style benchmarks"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=200,
        help="Number of benchmark pairs to generate (default: 200)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "data" / "trusthub_large",
        help="Output directory for benchmarks",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Verbosity level",
    )

    args = parser.parse_args()

    level = logging.WARNING
    if args.verbose >= 2:
        level = logging.DEBUG
    elif args.verbose >= 1:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    logger.info(f"Generating {args.count} benchmark pairs...")
    logger.info(f"Output directory: {args.output_dir}")

    generate_benchmarks(args.output_dir, args.count)

    # Count total lines
    total_lines = 0
    raw_dir = args.output_dir / "raw"
    if raw_dir.exists():
        for vfile in raw_dir.glob("**/*.v"):
            total_lines += sum(1 for _ in open(vfile))

    logger.info(f"Total lines of Verilog code: {total_lines:,}")
    logger.info("Generation complete!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
