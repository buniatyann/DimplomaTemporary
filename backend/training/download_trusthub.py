#!/usr/bin/env python3
"""Download TrustHub benchmarks for training.

TrustHub requires manual registration, but many benchmarks are also available
on GitHub mirrors and academic repositories. This script downloads from
available public sources.

Supported benchmarks with paired trojan/golden versions:
- Trust-Hub/Benchmarks on GitHub (gate-level netlists)
- ISCAS'89 benchmark circuits
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

logger = logging.getLogger(__name__)

# Public GitHub repositories with TrustHub-style benchmarks
GITHUB_SOURCES = {
    "trust-hub-benchmarks": {
        "url": "https://github.com/jinyier/TRIT-TC.git",
        "description": "Hardware Trojan benchmarks from TRIT-TC project",
    },
    "trusthub-rtl": {
        "url": "https://github.com/DfX-NYUAD/TrojanBenchmarks.git",
        "description": "NYU Abu Dhabi Trojan Benchmarks",
    },
}

# Sample Verilog files for testing when TrustHub is unavailable
SAMPLE_BENCHMARKS = {
    "AES-T100": {
        "trojan": '''// AES-T100: Trojan-infected AES module
// Trojan: Leaks key when specific plaintext pattern detected

module aes_cipher_top_trojan(
    input clk,
    input rst,
    input [127:0] plaintext,
    input [127:0] key,
    output reg [127:0] ciphertext,
    output reg done,
    output reg trojan_leak  // Trojan payload output
);

    // Normal AES registers
    reg [127:0] state;
    reg [3:0] round;

    // Trojan trigger: rare input pattern
    wire trojan_trigger;
    assign trojan_trigger = (plaintext[31:0] == 32'hDEADBEEF);

    // Trojan FSM counter
    reg [7:0] Trojan_Trigger_Counter;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= 128'b0;
            round <= 4'b0;
            done <= 1'b0;
            Trojan_Trigger_Counter <= 8'b0;
            trojan_leak <= 1'b0;
        end else begin
            // Normal AES operation (simplified)
            state <= plaintext ^ key;
            round <= round + 1;

            if (round == 4'd10) begin
                ciphertext <= state;
                done <= 1'b1;
            end

            // Trojan payload: leak key bit by bit
            if (trojan_trigger) begin
                Trojan_Trigger_Counter <= Trojan_Trigger_Counter + 1;
                trojan_leak <= key[Trojan_Trigger_Counter[6:0]];
            end
        end
    end

endmodule
''',
        "golden": '''// AES: Trojan-free golden reference

module aes_cipher_top(
    input clk,
    input rst,
    input [127:0] plaintext,
    input [127:0] key,
    output reg [127:0] ciphertext,
    output reg done
);

    // Normal AES registers
    reg [127:0] state;
    reg [3:0] round;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= 128'b0;
            round <= 4'b0;
            done <= 1'b0;
        end else begin
            // Normal AES operation (simplified)
            state <= plaintext ^ key;
            round <= round + 1;

            if (round == 4'd10) begin
                ciphertext <= state;
                done <= 1'b1;
            end
        end
    end

endmodule
'''
    },
    "AES-T200": {
        "trojan": '''// AES-T200: Sequential Trojan with counter-based trigger

module aes_t200(
    input clk,
    input rst,
    input [127:0] data_in,
    input [127:0] key,
    output reg [127:0] data_out,
    output reg valid
);

    reg [127:0] state;
    reg [3:0] round_cnt;

    // Trojan: Counter-based trigger
    reg [31:0] trigger_counter;
    reg trojan_active;
    wire Tj_trigger = (trigger_counter == 32'd1000000);

    // Trojan payload registers
    reg [7:0] Trojan_payload_reg;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= 128'b0;
            round_cnt <= 4'b0;
            valid <= 1'b0;
            trigger_counter <= 32'b0;
            trojan_active <= 1'b0;
            Trojan_payload_reg <= 8'b0;
        end else begin
            trigger_counter <= trigger_counter + 1;

            // Normal operation
            state <= data_in ^ key;
            round_cnt <= round_cnt + 1;

            if (round_cnt == 4'd10) begin
                // Trojan: corrupt output after trigger
                if (Tj_trigger || trojan_active) begin
                    trojan_active <= 1'b1;
                    Trojan_payload_reg <= key[7:0];
                    data_out <= state ^ {120'b0, Trojan_payload_reg};
                end else begin
                    data_out <= state;
                end
                valid <= 1'b1;
            end
        end
    end

endmodule
''',
        "golden": '''// AES-T200 Golden: Clean reference

module aes_t200_golden(
    input clk,
    input rst,
    input [127:0] data_in,
    input [127:0] key,
    output reg [127:0] data_out,
    output reg valid
);

    reg [127:0] state;
    reg [3:0] round_cnt;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= 128'b0;
            round_cnt <= 4'b0;
            valid <= 1'b0;
        end else begin
            state <= data_in ^ key;
            round_cnt <= round_cnt + 1;

            if (round_cnt == 4'd10) begin
                data_out <= state;
                valid <= 1'b1;
            end
        end
    end

endmodule
'''
    },
    "RS232-T100": {
        "trojan": '''// RS232-T100: UART Trojan leaking data

module uart_tx_trojan(
    input clk,
    input rst,
    input [7:0] data_in,
    input tx_start,
    output reg tx,
    output reg tx_busy,
    output reg trojan_out  // Covert channel
);

    reg [3:0] bit_cnt;
    reg [7:0] shift_reg;
    reg [15:0] baud_cnt;

    // Trojan: leak every 256th byte
    reg [7:0] leak_counter;
    wire trojan_trigger = (leak_counter == 8'hFF);
    reg [7:0] Trojan_data_capture;

    parameter BAUD_DIV = 16'd868;  // 115200 baud @ 100MHz

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            tx <= 1'b1;
            tx_busy <= 1'b0;
            bit_cnt <= 4'b0;
            shift_reg <= 8'b0;
            baud_cnt <= 16'b0;
            leak_counter <= 8'b0;
            trojan_out <= 1'b0;
            Trojan_data_capture <= 8'b0;
        end else begin
            if (tx_start && !tx_busy) begin
                tx_busy <= 1'b1;
                shift_reg <= data_in;
                bit_cnt <= 4'd10;
                baud_cnt <= 16'b0;
                leak_counter <= leak_counter + 1;

                // Trojan: capture data for covert leak
                if (trojan_trigger) begin
                    Trojan_data_capture <= data_in;
                end
            end else if (tx_busy) begin
                if (baud_cnt == BAUD_DIV) begin
                    baud_cnt <= 16'b0;
                    if (bit_cnt > 0) begin
                        tx <= (bit_cnt == 10) ? 1'b0 : shift_reg[0];
                        shift_reg <= {1'b1, shift_reg[7:1]};
                        bit_cnt <= bit_cnt - 1;
                    end else begin
                        tx_busy <= 1'b0;
                        tx <= 1'b1;
                    end
                end else begin
                    baud_cnt <= baud_cnt + 1;
                end
            end

            // Trojan covert channel output
            trojan_out <= Trojan_data_capture[leak_counter[2:0]];
        end
    end

endmodule
''',
        "golden": '''// RS232 Golden: Clean UART transmitter

module uart_tx(
    input clk,
    input rst,
    input [7:0] data_in,
    input tx_start,
    output reg tx,
    output reg tx_busy
);

    reg [3:0] bit_cnt;
    reg [7:0] shift_reg;
    reg [15:0] baud_cnt;

    parameter BAUD_DIV = 16'd868;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            tx <= 1'b1;
            tx_busy <= 1'b0;
            bit_cnt <= 4'b0;
            shift_reg <= 8'b0;
            baud_cnt <= 16'b0;
        end else begin
            if (tx_start && !tx_busy) begin
                tx_busy <= 1'b1;
                shift_reg <= data_in;
                bit_cnt <= 4'd10;
                baud_cnt <= 16'b0;
            end else if (tx_busy) begin
                if (baud_cnt == BAUD_DIV) begin
                    baud_cnt <= 16'b0;
                    if (bit_cnt > 0) begin
                        tx <= (bit_cnt == 10) ? 1'b0 : shift_reg[0];
                        shift_reg <= {1'b1, shift_reg[7:1]};
                        bit_cnt <= bit_cnt - 1;
                    end else begin
                        tx_busy <= 1'b0;
                        tx <= 1'b1;
                    end
                end else begin
                    baud_cnt <= baud_cnt + 1;
                end
            end
        end
    end

endmodule
'''
    },
    "RS232-T200": {
        "trojan": '''// RS232-T200: Baud rate manipulation Trojan

module uart_rx_trojan(
    input clk,
    input rst,
    input rx,
    output reg [7:0] data_out,
    output reg rx_valid,
    output reg rx_error
);

    reg [3:0] bit_cnt;
    reg [7:0] shift_reg;
    reg [15:0] baud_cnt;
    reg receiving;

    // Trojan: manipulate baud rate on specific pattern
    reg [23:0] pattern_detect;
    wire mal_trigger = (pattern_detect == 24'hABCDEF);
    reg [15:0] Trojan_baud_modifier;

    parameter BAUD_DIV = 16'd868;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            data_out <= 8'b0;
            rx_valid <= 1'b0;
            rx_error <= 1'b0;
            bit_cnt <= 4'b0;
            shift_reg <= 8'b0;
            baud_cnt <= 16'b0;
            receiving <= 1'b0;
            pattern_detect <= 24'b0;
            Trojan_baud_modifier <= 16'b0;
        end else begin
            rx_valid <= 1'b0;

            if (!receiving && !rx) begin
                receiving <= 1'b1;
                bit_cnt <= 4'd8;
                baud_cnt <= (BAUD_DIV >> 1) + Trojan_baud_modifier;
            end else if (receiving) begin
                if (baud_cnt == 0) begin
                    baud_cnt <= BAUD_DIV + Trojan_baud_modifier;
                    if (bit_cnt > 0) begin
                        shift_reg <= {rx, shift_reg[7:1]};
                        bit_cnt <= bit_cnt - 1;
                    end else begin
                        receiving <= 1'b0;
                        data_out <= shift_reg;
                        rx_valid <= 1'b1;
                        pattern_detect <= {pattern_detect[15:0], shift_reg};

                        // Trojan: activate on pattern
                        if (mal_trigger) begin
                            Trojan_baud_modifier <= 16'd100;  // Cause framing errors
                        end
                    end
                end else begin
                    baud_cnt <= baud_cnt - 1;
                end
            end
        end
    end

endmodule
''',
        "golden": '''// RS232-T200 Golden: Clean UART receiver

module uart_rx(
    input clk,
    input rst,
    input rx,
    output reg [7:0] data_out,
    output reg rx_valid,
    output reg rx_error
);

    reg [3:0] bit_cnt;
    reg [7:0] shift_reg;
    reg [15:0] baud_cnt;
    reg receiving;

    parameter BAUD_DIV = 16'd868;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            data_out <= 8'b0;
            rx_valid <= 1'b0;
            rx_error <= 1'b0;
            bit_cnt <= 4'b0;
            shift_reg <= 8'b0;
            baud_cnt <= 16'b0;
            receiving <= 1'b0;
        end else begin
            rx_valid <= 1'b0;

            if (!receiving && !rx) begin
                receiving <= 1'b1;
                bit_cnt <= 4'd8;
                baud_cnt <= BAUD_DIV >> 1;
            end else if (receiving) begin
                if (baud_cnt == 0) begin
                    baud_cnt <= BAUD_DIV;
                    if (bit_cnt > 0) begin
                        shift_reg <= {rx, shift_reg[7:1]};
                        bit_cnt <= bit_cnt - 1;
                    end else begin
                        receiving <= 1'b0;
                        data_out <= shift_reg;
                        rx_valid <= 1'b1;
                    end
                end else begin
                    baud_cnt <= baud_cnt - 1;
                end
            end
        end
    end

endmodule
'''
    },
    "BasicRSA-T100": {
        "trojan": '''// BasicRSA-T100: RSA key leakage Trojan

module rsa_core_trojan(
    input clk,
    input rst,
    input start,
    input [63:0] message,
    input [63:0] exponent,
    input [63:0] modulus,
    output reg [63:0] result,
    output reg done,
    output reg key_leak  // Trojan output
);

    reg [63:0] base;
    reg [63:0] exp_reg;
    reg [63:0] acc;
    reg [6:0] bit_idx;
    reg computing;

    // Trojan: leak exponent (private key) bits
    reg [7:0] Trojan_leak_counter;
    wire ht_trigger = (message[7:0] == 8'h42);

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            result <= 64'b0;
            done <= 1'b0;
            base <= 64'b0;
            exp_reg <= 64'b0;
            acc <= 64'b1;
            bit_idx <= 7'b0;
            computing <= 1'b0;
            Trojan_leak_counter <= 8'b0;
            key_leak <= 1'b0;
        end else begin
            done <= 1'b0;

            if (start && !computing) begin
                computing <= 1'b1;
                base <= message;
                exp_reg <= exponent;
                acc <= 64'b1;
                bit_idx <= 7'd63;

                // Trojan activation
                if (ht_trigger) begin
                    Trojan_leak_counter <= Trojan_leak_counter + 1;
                end
            end else if (computing) begin
                // Simplified modular exponentiation
                if (exp_reg[bit_idx]) begin
                    acc <= (acc * base) % modulus;
                end
                base <= (base * base) % modulus;

                if (bit_idx == 0) begin
                    computing <= 1'b0;
                    result <= acc;
                    done <= 1'b1;
                end else begin
                    bit_idx <= bit_idx - 1;
                end
            end

            // Trojan: leak key bit
            key_leak <= exponent[Trojan_leak_counter[5:0]];
        end
    end

endmodule
''',
        "golden": '''// BasicRSA Golden: Clean RSA core

module rsa_core(
    input clk,
    input rst,
    input start,
    input [63:0] message,
    input [63:0] exponent,
    input [63:0] modulus,
    output reg [63:0] result,
    output reg done
);

    reg [63:0] base;
    reg [63:0] exp_reg;
    reg [63:0] acc;
    reg [6:0] bit_idx;
    reg computing;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            result <= 64'b0;
            done <= 1'b0;
            base <= 64'b0;
            exp_reg <= 64'b0;
            acc <= 64'b1;
            bit_idx <= 7'b0;
            computing <= 1'b0;
        end else begin
            done <= 1'b0;

            if (start && !computing) begin
                computing <= 1'b1;
                base <= message;
                exp_reg <= exponent;
                acc <= 64'b1;
                bit_idx <= 7'd63;
            end else if (computing) begin
                if (exp_reg[bit_idx]) begin
                    acc <= (acc * base) % modulus;
                end
                base <= (base * base) % modulus;

                if (bit_idx == 0) begin
                    computing <= 1'b0;
                    result <= acc;
                    done <= 1'b1;
                end else begin
                    bit_idx <= bit_idx - 1;
                end
            end
        end
    end

endmodule
'''
    },
    "s15850-T100": {
        "trojan": '''// s15850-T100: ISCAS benchmark with rare-event Trojan

module s15850_trojan(
    input clk,
    input rst,
    input [76:0] primary_inputs,
    output reg [149:0] primary_outputs,
    output reg backdoor_active
);

    reg [149:0] state_reg;
    reg [31:0] rare_counter;

    // Trojan trigger: extremely rare input combination
    wire trigger_condition = (primary_inputs[31:0] == 32'hCAFEBABE) &&
                            (primary_inputs[63:32] == 32'hDEADC0DE);

    // Trojan state machine
    reg [2:0] Trojan_FSM_state;
    reg [7:0] payload_counter;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state_reg <= 150'b0;
            primary_outputs <= 150'b0;
            rare_counter <= 32'b0;
            Trojan_FSM_state <= 3'b0;
            payload_counter <= 8'b0;
            backdoor_active <= 1'b0;
        end else begin
            // Normal ISCAS logic (simplified combinational)
            state_reg <= {primary_inputs, state_reg[149:77]} ^
                        {state_reg[72:0], primary_inputs};
            primary_outputs <= state_reg;

            // Trojan FSM
            case (Trojan_FSM_state)
                3'd0: begin
                    if (trigger_condition) begin
                        Trojan_FSM_state <= 3'd1;
                        rare_counter <= rare_counter + 1;
                    end
                end
                3'd1: begin
                    payload_counter <= payload_counter + 1;
                    if (payload_counter == 8'hFF) begin
                        Trojan_FSM_state <= 3'd2;
                        backdoor_active <= 1'b1;
                    end
                end
                3'd2: begin
                    // Trojan payload: corrupt outputs
                    primary_outputs <= state_reg ^ {150{backdoor_active}};
                end
                default: Trojan_FSM_state <= 3'd0;
            endcase
        end
    end

endmodule
''',
        "golden": '''// s15850 Golden: Clean ISCAS benchmark

module s15850(
    input clk,
    input rst,
    input [76:0] primary_inputs,
    output reg [149:0] primary_outputs
);

    reg [149:0] state_reg;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state_reg <= 150'b0;
            primary_outputs <= 150'b0;
        end else begin
            state_reg <= {primary_inputs, state_reg[149:77]} ^
                        {state_reg[72:0], primary_inputs};
            primary_outputs <= state_reg;
        end
    end

endmodule
'''
    },
    # Additional benchmarks for expanded dataset
    "SHA256-T100": {
        "trojan": '''// SHA256-T100: Hash function with collision Trojan

module sha256_trojan(
    input clk,
    input rst,
    input [511:0] block_in,
    input start,
    output reg [255:0] hash_out,
    output reg done
);

    reg [255:0] hash_state;
    reg [5:0] round;
    reg computing;

    // Trojan: produce weak hash on specific input prefix
    wire Trojan_trigger = (block_in[511:480] == 32'hBAADF00D);
    reg [31:0] Tj_counter;
    reg Trojan_weaken_hash;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            hash_state <= 256'h6a09e667bb67ae853c6ef372a54ff53a510e527f9b05688c1f83d9ab5be0cd19;
            hash_out <= 256'b0;
            done <= 1'b0;
            round <= 6'b0;
            computing <= 1'b0;
            Tj_counter <= 32'b0;
            Trojan_weaken_hash <= 1'b0;
        end else begin
            done <= 1'b0;

            if (start && !computing) begin
                computing <= 1'b1;
                round <= 6'b0;
                hash_state <= 256'h6a09e667bb67ae853c6ef372a54ff53a510e527f9b05688c1f83d9ab5be0cd19;

                if (Trojan_trigger) begin
                    Tj_counter <= Tj_counter + 1;
                    if (Tj_counter > 32'd100) begin
                        Trojan_weaken_hash <= 1'b1;
                    end
                end
            end else if (computing) begin
                // Simplified SHA rounds
                hash_state <= hash_state ^ {block_in[255:0], block_in[511:256]};
                round <= round + 1;

                if (round == 6'd63) begin
                    computing <= 1'b0;
                    // Trojan payload: reduce hash entropy
                    if (Trojan_weaken_hash) begin
                        hash_out <= {128'b0, hash_state[127:0]};  // Zero upper bits
                    end else begin
                        hash_out <= hash_state;
                    end
                    done <= 1'b1;
                end
            end
        end
    end

endmodule
''',
        "golden": '''// SHA256 Golden: Clean implementation

module sha256(
    input clk,
    input rst,
    input [511:0] block_in,
    input start,
    output reg [255:0] hash_out,
    output reg done
);

    reg [255:0] hash_state;
    reg [5:0] round;
    reg computing;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            hash_state <= 256'h6a09e667bb67ae853c6ef372a54ff53a510e527f9b05688c1f83d9ab5be0cd19;
            hash_out <= 256'b0;
            done <= 1'b0;
            round <= 6'b0;
            computing <= 1'b0;
        end else begin
            done <= 1'b0;

            if (start && !computing) begin
                computing <= 1'b1;
                round <= 6'b0;
                hash_state <= 256'h6a09e667bb67ae853c6ef372a54ff53a510e527f9b05688c1f83d9ab5be0cd19;
            end else if (computing) begin
                hash_state <= hash_state ^ {block_in[255:0], block_in[511:256]};
                round <= round + 1;

                if (round == 6'd63) begin
                    computing <= 1'b0;
                    hash_out <= hash_state;
                    done <= 1'b1;
                end
            end
        end
    end

endmodule
'''
    },
    "I2C-T100": {
        "trojan": '''// I2C-T100: I2C controller with address sniffing Trojan

module i2c_master_trojan(
    input clk,
    input rst,
    input [6:0] slave_addr,
    input [7:0] data_in,
    input start_xfer,
    input rw,
    output reg scl,
    output reg sda_out,
    input sda_in,
    output reg [7:0] data_out,
    output reg busy,
    output reg ack_error
);

    reg [3:0] state;
    reg [3:0] bit_cnt;
    reg [7:0] shift_reg;
    reg [15:0] clk_div;

    // Trojan: capture addresses and data
    reg [6:0] Trojan_addr_capture [0:15];
    reg [7:0] Trojan_data_capture [0:15];
    reg [3:0] capture_idx;
    wire trigger_capture = (slave_addr == 7'h50);  // EEPROM address

    parameter CLK_DIV = 16'd250;  // 100kHz I2C

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= 4'd0;
            bit_cnt <= 4'b0;
            shift_reg <= 8'b0;
            clk_div <= 16'b0;
            scl <= 1'b1;
            sda_out <= 1'b1;
            data_out <= 8'b0;
            busy <= 1'b0;
            ack_error <= 1'b0;
            capture_idx <= 4'b0;
        end else begin
            if (clk_div == CLK_DIV) begin
                clk_div <= 16'b0;
                scl <= ~scl;

                case (state)
                    4'd0: begin  // IDLE
                        if (start_xfer && !busy) begin
                            busy <= 1'b1;
                            state <= 4'd1;
                            shift_reg <= {slave_addr, rw};
                            bit_cnt <= 4'd8;
                            sda_out <= 1'b0;  // START

                            // Trojan: log access
                            if (trigger_capture) begin
                                Trojan_addr_capture[capture_idx] <= slave_addr;
                                Trojan_data_capture[capture_idx] <= data_in;
                                capture_idx <= capture_idx + 1;
                            end
                        end
                    end
                    4'd1: begin  // SEND ADDRESS
                        if (scl) begin
                            sda_out <= shift_reg[7];
                            shift_reg <= {shift_reg[6:0], 1'b1};
                            bit_cnt <= bit_cnt - 1;
                            if (bit_cnt == 0) state <= 4'd2;
                        end
                    end
                    4'd2: begin  // ACK
                        if (scl) begin
                            ack_error <= sda_in;
                            if (!rw) begin
                                state <= 4'd3;
                                shift_reg <= data_in;
                                bit_cnt <= 4'd8;
                            end else begin
                                state <= 4'd4;
                                bit_cnt <= 4'd8;
                            end
                        end
                    end
                    4'd3: begin  // WRITE DATA
                        if (scl) begin
                            sda_out <= shift_reg[7];
                            shift_reg <= {shift_reg[6:0], 1'b1};
                            bit_cnt <= bit_cnt - 1;
                            if (bit_cnt == 0) state <= 4'd5;
                        end
                    end
                    4'd4: begin  // READ DATA
                        if (scl) begin
                            shift_reg <= {shift_reg[6:0], sda_in};
                            bit_cnt <= bit_cnt - 1;
                            if (bit_cnt == 0) begin
                                data_out <= shift_reg;
                                state <= 4'd5;
                            end
                        end
                    end
                    4'd5: begin  // STOP
                        sda_out <= 1'b1;
                        busy <= 1'b0;
                        state <= 4'd0;
                    end
                endcase
            end else begin
                clk_div <= clk_div + 1;
            end
        end
    end

endmodule
''',
        "golden": '''// I2C Golden: Clean I2C master

module i2c_master(
    input clk,
    input rst,
    input [6:0] slave_addr,
    input [7:0] data_in,
    input start_xfer,
    input rw,
    output reg scl,
    output reg sda_out,
    input sda_in,
    output reg [7:0] data_out,
    output reg busy,
    output reg ack_error
);

    reg [3:0] state;
    reg [3:0] bit_cnt;
    reg [7:0] shift_reg;
    reg [15:0] clk_div;

    parameter CLK_DIV = 16'd250;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= 4'd0;
            bit_cnt <= 4'b0;
            shift_reg <= 8'b0;
            clk_div <= 16'b0;
            scl <= 1'b1;
            sda_out <= 1'b1;
            data_out <= 8'b0;
            busy <= 1'b0;
            ack_error <= 1'b0;
        end else begin
            if (clk_div == CLK_DIV) begin
                clk_div <= 16'b0;
                scl <= ~scl;

                case (state)
                    4'd0: begin
                        if (start_xfer && !busy) begin
                            busy <= 1'b1;
                            state <= 4'd1;
                            shift_reg <= {slave_addr, rw};
                            bit_cnt <= 4'd8;
                            sda_out <= 1'b0;
                        end
                    end
                    4'd1: begin
                        if (scl) begin
                            sda_out <= shift_reg[7];
                            shift_reg <= {shift_reg[6:0], 1'b1};
                            bit_cnt <= bit_cnt - 1;
                            if (bit_cnt == 0) state <= 4'd2;
                        end
                    end
                    4'd2: begin
                        if (scl) begin
                            ack_error <= sda_in;
                            if (!rw) begin
                                state <= 4'd3;
                                shift_reg <= data_in;
                                bit_cnt <= 4'd8;
                            end else begin
                                state <= 4'd4;
                                bit_cnt <= 4'd8;
                            end
                        end
                    end
                    4'd3: begin
                        if (scl) begin
                            sda_out <= shift_reg[7];
                            shift_reg <= {shift_reg[6:0], 1'b1};
                            bit_cnt <= bit_cnt - 1;
                            if (bit_cnt == 0) state <= 4'd5;
                        end
                    end
                    4'd4: begin
                        if (scl) begin
                            shift_reg <= {shift_reg[6:0], sda_in};
                            bit_cnt <= bit_cnt - 1;
                            if (bit_cnt == 0) begin
                                data_out <= shift_reg;
                                state <= 4'd5;
                            end
                        end
                    end
                    4'd5: begin
                        sda_out <= 1'b1;
                        busy <= 1'b0;
                        state <= 4'd0;
                    end
                endcase
            end else begin
                clk_div <= clk_div + 1;
            end
        end
    end

endmodule
'''
    },
    "SPI-T100": {
        "trojan": '''// SPI-T100: SPI controller with data exfiltration Trojan

module spi_master_trojan(
    input clk,
    input rst,
    input [7:0] data_in,
    input start,
    input cpol,
    input cpha,
    output reg sclk,
    output reg mosi,
    input miso,
    output reg ss_n,
    output reg [7:0] data_out,
    output reg done
);

    reg [2:0] bit_cnt;
    reg [7:0] tx_shift;
    reg [7:0] rx_shift;
    reg [7:0] clk_cnt;
    reg active;

    // Trojan: leak data on covert timing channel
    reg [7:0] Trojan_leak_buffer;
    reg [15:0] leak_counter;
    wire ht_active = (leak_counter[15:8] == data_in);

    parameter CLK_DIV = 8'd10;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            sclk <= cpol;
            mosi <= 1'b0;
            ss_n <= 1'b1;
            data_out <= 8'b0;
            done <= 1'b0;
            bit_cnt <= 3'b0;
            tx_shift <= 8'b0;
            rx_shift <= 8'b0;
            clk_cnt <= 8'b0;
            active <= 1'b0;
            Trojan_leak_buffer <= 8'b0;
            leak_counter <= 16'b0;
        end else begin
            done <= 1'b0;

            if (start && !active) begin
                active <= 1'b1;
                ss_n <= 1'b0;
                tx_shift <= data_in;
                bit_cnt <= 3'd7;
                clk_cnt <= 8'b0;
                sclk <= cpol;

                // Trojan: capture data
                Trojan_leak_buffer <= data_in;
                leak_counter <= leak_counter + 1;
            end else if (active) begin
                clk_cnt <= clk_cnt + 1;

                if (clk_cnt == CLK_DIV) begin
                    clk_cnt <= 8'b0;
                    sclk <= ~sclk;

                    if (sclk == cpol) begin
                        mosi <= tx_shift[7];
                        tx_shift <= {tx_shift[6:0], 1'b0};
                    end else begin
                        rx_shift <= {rx_shift[6:0], miso};

                        if (bit_cnt == 0) begin
                            active <= 1'b0;
                            ss_n <= 1'b1;
                            data_out <= rx_shift;
                            done <= 1'b1;
                            sclk <= cpol;
                        end else begin
                            bit_cnt <= bit_cnt - 1;
                        end
                    end
                end

                // Trojan: timing-based leak
                if (ht_active) begin
                    // Slightly delay SCLK edge
                    clk_cnt <= clk_cnt;  // Stall one cycle
                end
            end
        end
    end

endmodule
''',
        "golden": '''// SPI Golden: Clean SPI master

module spi_master(
    input clk,
    input rst,
    input [7:0] data_in,
    input start,
    input cpol,
    input cpha,
    output reg sclk,
    output reg mosi,
    input miso,
    output reg ss_n,
    output reg [7:0] data_out,
    output reg done
);

    reg [2:0] bit_cnt;
    reg [7:0] tx_shift;
    reg [7:0] rx_shift;
    reg [7:0] clk_cnt;
    reg active;

    parameter CLK_DIV = 8'd10;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            sclk <= cpol;
            mosi <= 1'b0;
            ss_n <= 1'b1;
            data_out <= 8'b0;
            done <= 1'b0;
            bit_cnt <= 3'b0;
            tx_shift <= 8'b0;
            rx_shift <= 8'b0;
            clk_cnt <= 8'b0;
            active <= 1'b0;
        end else begin
            done <= 1'b0;

            if (start && !active) begin
                active <= 1'b1;
                ss_n <= 1'b0;
                tx_shift <= data_in;
                bit_cnt <= 3'd7;
                clk_cnt <= 8'b0;
                sclk <= cpol;
            end else if (active) begin
                clk_cnt <= clk_cnt + 1;

                if (clk_cnt == CLK_DIV) begin
                    clk_cnt <= 8'b0;
                    sclk <= ~sclk;

                    if (sclk == cpol) begin
                        mosi <= tx_shift[7];
                        tx_shift <= {tx_shift[6:0], 1'b0};
                    end else begin
                        rx_shift <= {rx_shift[6:0], miso};

                        if (bit_cnt == 0) begin
                            active <= 1'b0;
                            ss_n <= 1'b1;
                            data_out <= rx_shift;
                            done <= 1'b1;
                            sclk <= cpol;
                        end else begin
                            bit_cnt <= bit_cnt - 1;
                        end
                    end
                end
            end
        end
    end

endmodule
'''
    },
    "FIFO-T100": {
        "trojan": '''// FIFO-T100: FIFO with data corruption Trojan

module fifo_trojan #(
    parameter DEPTH = 16,
    parameter WIDTH = 8
)(
    input clk,
    input rst,
    input [WIDTH-1:0] data_in,
    input wr_en,
    input rd_en,
    output reg [WIDTH-1:0] data_out,
    output reg full,
    output reg empty
);

    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [3:0] wr_ptr;
    reg [3:0] rd_ptr;
    reg [4:0] count;

    // Trojan: corrupt data after pattern seen
    reg [7:0] pattern_match_cnt;
    wire Trojan_trigger = (data_in == 8'hA5);
    reg Trojan_corrupt_mode;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            wr_ptr <= 4'b0;
            rd_ptr <= 4'b0;
            count <= 5'b0;
            data_out <= {WIDTH{1'b0}};
            full <= 1'b0;
            empty <= 1'b1;
            pattern_match_cnt <= 8'b0;
            Trojan_corrupt_mode <= 1'b0;
        end else begin
            // Write
            if (wr_en && !full) begin
                mem[wr_ptr] <= data_in;
                wr_ptr <= wr_ptr + 1;
                count <= count + 1;

                // Trojan: count pattern occurrences
                if (Trojan_trigger) begin
                    pattern_match_cnt <= pattern_match_cnt + 1;
                    if (pattern_match_cnt >= 8'd10) begin
                        Trojan_corrupt_mode <= 1'b1;
                    end
                end
            end

            // Read
            if (rd_en && !empty) begin
                // Trojan: corrupt output data
                if (Trojan_corrupt_mode) begin
                    data_out <= mem[rd_ptr] ^ 8'hFF;  // Flip all bits
                end else begin
                    data_out <= mem[rd_ptr];
                end
                rd_ptr <= rd_ptr + 1;
                count <= count - 1;
            end

            // Both read and write
            if (wr_en && !full && rd_en && !empty) begin
                count <= count;  // No net change
            end

            full <= (count == DEPTH);
            empty <= (count == 0);
        end
    end

endmodule
''',
        "golden": '''// FIFO Golden: Clean FIFO

module fifo #(
    parameter DEPTH = 16,
    parameter WIDTH = 8
)(
    input clk,
    input rst,
    input [WIDTH-1:0] data_in,
    input wr_en,
    input rd_en,
    output reg [WIDTH-1:0] data_out,
    output reg full,
    output reg empty
);

    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [3:0] wr_ptr;
    reg [3:0] rd_ptr;
    reg [4:0] count;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            wr_ptr <= 4'b0;
            rd_ptr <= 4'b0;
            count <= 5'b0;
            data_out <= {WIDTH{1'b0}};
            full <= 1'b0;
            empty <= 1'b1;
        end else begin
            if (wr_en && !full) begin
                mem[wr_ptr] <= data_in;
                wr_ptr <= wr_ptr + 1;
                count <= count + 1;
            end

            if (rd_en && !empty) begin
                data_out <= mem[rd_ptr];
                rd_ptr <= rd_ptr + 1;
                count <= count - 1;
            end

            if (wr_en && !full && rd_en && !empty) begin
                count <= count;
            end

            full <= (count == DEPTH);
            empty <= (count == 0);
        end
    end

endmodule
'''
    },
    "PWM-T100": {
        "trojan": '''// PWM-T100: PWM controller with duty cycle manipulation Trojan

module pwm_trojan(
    input clk,
    input rst,
    input [7:0] duty_cycle,
    input enable,
    output reg pwm_out,
    output reg trojan_active
);

    reg [7:0] counter;
    reg [31:0] cycle_count;

    // Trojan: change duty cycle after many cycles
    wire Tj_trigger = (cycle_count >= 32'd1000000);
    reg [7:0] Trojan_duty_offset;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            counter <= 8'b0;
            pwm_out <= 1'b0;
            cycle_count <= 32'b0;
            Trojan_duty_offset <= 8'b0;
            trojan_active <= 1'b0;
        end else if (enable) begin
            counter <= counter + 1;

            if (counter == 8'hFF) begin
                cycle_count <= cycle_count + 1;
            end

            // Trojan: gradually increase duty offset
            if (Tj_trigger && counter == 8'b0) begin
                trojan_active <= 1'b1;
                if (Trojan_duty_offset < 8'd50) begin
                    Trojan_duty_offset <= Trojan_duty_offset + 1;
                end
            end

            // PWM output with trojan modification
            if (counter < (duty_cycle + Trojan_duty_offset)) begin
                pwm_out <= 1'b1;
            end else begin
                pwm_out <= 1'b0;
            end
        end else begin
            pwm_out <= 1'b0;
        end
    end

endmodule
''',
        "golden": '''// PWM Golden: Clean PWM controller

module pwm(
    input clk,
    input rst,
    input [7:0] duty_cycle,
    input enable,
    output reg pwm_out
);

    reg [7:0] counter;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            counter <= 8'b0;
            pwm_out <= 1'b0;
        end else if (enable) begin
            counter <= counter + 1;

            if (counter < duty_cycle) begin
                pwm_out <= 1'b1;
            end else begin
                pwm_out <= 1'b0;
            end
        end else begin
            pwm_out <= 1'b0;
        end
    end

endmodule
'''
    },
    "Timer-T100": {
        "trojan": '''// Timer-T100: Timer with interrupt manipulation Trojan

module timer_trojan(
    input clk,
    input rst,
    input [31:0] compare_val,
    input enable,
    input clear,
    output reg [31:0] count,
    output reg interrupt,
    output reg backdoor_int
);

    reg [15:0] hidden_counter;

    // Trojan: generate spurious interrupts
    wire mal_trigger = (hidden_counter == 16'hDEAD);
    reg Trojan_int_enable;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            count <= 32'b0;
            interrupt <= 1'b0;
            hidden_counter <= 16'b0;
            Trojan_int_enable <= 1'b0;
            backdoor_int <= 1'b0;
        end else begin
            interrupt <= 1'b0;
            backdoor_int <= 1'b0;

            if (clear) begin
                count <= 32'b0;
            end else if (enable) begin
                count <= count + 1;
                hidden_counter <= hidden_counter + 1;

                if (count == compare_val) begin
                    interrupt <= 1'b1;
                    count <= 32'b0;
                end

                // Trojan: enable spurious interrupt mode
                if (mal_trigger) begin
                    Trojan_int_enable <= 1'b1;
                end

                // Trojan: generate unexpected interrupt
                if (Trojan_int_enable && (count[7:0] == 8'hAA)) begin
                    backdoor_int <= 1'b1;
                end
            end
        end
    end

endmodule
''',
        "golden": '''// Timer Golden: Clean timer

module timer(
    input clk,
    input rst,
    input [31:0] compare_val,
    input enable,
    input clear,
    output reg [31:0] count,
    output reg interrupt
);

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            count <= 32'b0;
            interrupt <= 1'b0;
        end else begin
            interrupt <= 1'b0;

            if (clear) begin
                count <= 32'b0;
            end else if (enable) begin
                count <= count + 1;

                if (count == compare_val) begin
                    interrupt <= 1'b1;
                    count <= 32'b0;
                end
            end
        end
    end

endmodule
'''
    },
    "DMA-T100": {
        "trojan": '''// DMA-T100: DMA controller with memory snooping Trojan

module dma_trojan(
    input clk,
    input rst,
    input [31:0] src_addr,
    input [31:0] dst_addr,
    input [15:0] length,
    input start,
    output reg [31:0] mem_addr,
    output reg [31:0] mem_wdata,
    input [31:0] mem_rdata,
    output reg mem_rd,
    output reg mem_wr,
    output reg busy,
    output reg done
);

    reg [31:0] current_src;
    reg [31:0] current_dst;
    reg [15:0] remaining;
    reg [1:0] state;
    reg [31:0] data_buffer;

    // Trojan: snoop and store memory contents
    reg [31:0] Trojan_snoop_buffer [0:7];
    reg [2:0] snoop_idx;
    wire ht_snoop_trigger = (src_addr[31:24] == 8'hFF);  // High memory region

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            mem_addr <= 32'b0;
            mem_wdata <= 32'b0;
            mem_rd <= 1'b0;
            mem_wr <= 1'b0;
            busy <= 1'b0;
            done <= 1'b0;
            current_src <= 32'b0;
            current_dst <= 32'b0;
            remaining <= 16'b0;
            state <= 2'b0;
            data_buffer <= 32'b0;
            snoop_idx <= 3'b0;
        end else begin
            done <= 1'b0;
            mem_rd <= 1'b0;
            mem_wr <= 1'b0;

            case (state)
                2'd0: begin  // IDLE
                    if (start && !busy) begin
                        busy <= 1'b1;
                        current_src <= src_addr;
                        current_dst <= dst_addr;
                        remaining <= length;
                        state <= 2'd1;
                    end
                end
                2'd1: begin  // READ
                    mem_addr <= current_src;
                    mem_rd <= 1'b1;
                    state <= 2'd2;
                end
                2'd2: begin  // CAPTURE
                    data_buffer <= mem_rdata;

                    // Trojan: snoop high memory
                    if (ht_snoop_trigger) begin
                        Trojan_snoop_buffer[snoop_idx] <= mem_rdata;
                        snoop_idx <= snoop_idx + 1;
                    end

                    state <= 2'd3;
                end
                2'd3: begin  // WRITE
                    mem_addr <= current_dst;
                    mem_wdata <= data_buffer;
                    mem_wr <= 1'b1;

                    current_src <= current_src + 4;
                    current_dst <= current_dst + 4;
                    remaining <= remaining - 1;

                    if (remaining == 1) begin
                        state <= 2'd0;
                        busy <= 1'b0;
                        done <= 1'b1;
                    end else begin
                        state <= 2'd1;
                    end
                end
            endcase
        end
    end

endmodule
''',
        "golden": '''// DMA Golden: Clean DMA controller

module dma(
    input clk,
    input rst,
    input [31:0] src_addr,
    input [31:0] dst_addr,
    input [15:0] length,
    input start,
    output reg [31:0] mem_addr,
    output reg [31:0] mem_wdata,
    input [31:0] mem_rdata,
    output reg mem_rd,
    output reg mem_wr,
    output reg busy,
    output reg done
);

    reg [31:0] current_src;
    reg [31:0] current_dst;
    reg [15:0] remaining;
    reg [1:0] state;
    reg [31:0] data_buffer;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            mem_addr <= 32'b0;
            mem_wdata <= 32'b0;
            mem_rd <= 1'b0;
            mem_wr <= 1'b0;
            busy <= 1'b0;
            done <= 1'b0;
            current_src <= 32'b0;
            current_dst <= 32'b0;
            remaining <= 16'b0;
            state <= 2'b0;
            data_buffer <= 32'b0;
        end else begin
            done <= 1'b0;
            mem_rd <= 1'b0;
            mem_wr <= 1'b0;

            case (state)
                2'd0: begin
                    if (start && !busy) begin
                        busy <= 1'b1;
                        current_src <= src_addr;
                        current_dst <= dst_addr;
                        remaining <= length;
                        state <= 2'd1;
                    end
                end
                2'd1: begin
                    mem_addr <= current_src;
                    mem_rd <= 1'b1;
                    state <= 2'd2;
                end
                2'd2: begin
                    data_buffer <= mem_rdata;
                    state <= 2'd3;
                end
                2'd3: begin
                    mem_addr <= current_dst;
                    mem_wdata <= data_buffer;
                    mem_wr <= 1'b1;

                    current_src <= current_src + 4;
                    current_dst <= current_dst + 4;
                    remaining <= remaining - 1;

                    if (remaining == 1) begin
                        state <= 2'd0;
                        busy <= 1'b0;
                        done <= 1'b1;
                    end else begin
                        state <= 2'd1;
                    end
                end
            endcase
        end
    end

endmodule
'''
    },
    "AES-T300": {
        "trojan": '''// AES-T300: AES with kill switch Trojan

module aes_killswitch(
    input clk,
    input rst,
    input [127:0] data_in,
    input [127:0] key,
    input encrypt,
    output reg [127:0] data_out,
    output reg valid
);

    reg [127:0] state;
    reg [3:0] round;
    reg processing;

    // Trojan: kill switch - disable encryption permanently
    reg [63:0] Trojan_kill_sequence;
    wire kill_trigger = (Trojan_kill_sequence == 64'hDEADBEEFCAFEBABE);
    reg kill_active;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= 128'b0;
            data_out <= 128'b0;
            valid <= 1'b0;
            round <= 4'b0;
            processing <= 1'b0;
            Trojan_kill_sequence <= 64'b0;
            kill_active <= 1'b0;
        end else begin
            valid <= 1'b0;

            // Trojan: build kill sequence
            Trojan_kill_sequence <= {Trojan_kill_sequence[55:0], data_in[7:0]};

            if (kill_trigger) begin
                kill_active <= 1'b1;
            end

            if (encrypt && !processing) begin
                processing <= 1'b1;
                // Trojan: if killed, pass through plaintext
                if (kill_active) begin
                    state <= data_in;
                end else begin
                    state <= data_in ^ key;
                end
                round <= 4'd1;
            end else if (processing) begin
                // Simplified AES rounds
                if (!kill_active) begin
                    state <= state ^ {key[63:0], key[127:64]};
                end
                round <= round + 1;

                if (round == 4'd10) begin
                    processing <= 1'b0;
                    data_out <= state;
                    valid <= 1'b1;
                end
            end
        end
    end

endmodule
''',
        "golden": '''// AES-T300 Golden: Clean AES

module aes_clean(
    input clk,
    input rst,
    input [127:0] data_in,
    input [127:0] key,
    input encrypt,
    output reg [127:0] data_out,
    output reg valid
);

    reg [127:0] state;
    reg [3:0] round;
    reg processing;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= 128'b0;
            data_out <= 128'b0;
            valid <= 1'b0;
            round <= 4'b0;
            processing <= 1'b0;
        end else begin
            valid <= 1'b0;

            if (encrypt && !processing) begin
                processing <= 1'b1;
                state <= data_in ^ key;
                round <= 4'd1;
            end else if (processing) begin
                state <= state ^ {key[63:0], key[127:64]};
                round <= round + 1;

                if (round == 4'd10) begin
                    processing <= 1'b0;
                    data_out <= state;
                    valid <= 1'b1;
                end
            end
        end
    end

endmodule
'''
    },
    "GPIO-T100": {
        "trojan": '''// GPIO-T100: GPIO controller with covert channel

module gpio_trojan(
    input clk,
    input rst,
    input [7:0] data_in,
    input [7:0] dir,  // 1=output, 0=input
    output reg [7:0] data_out,
    input [7:0] pins_in,
    output reg [7:0] pins_out
);

    reg [7:0] output_reg;
    reg [7:0] input_reg;

    // Trojan: covert channel through GPIO timing
    reg [15:0] Trojan_timer;
    reg [7:0] leak_data;
    wire trigger_leak = (data_in == 8'hCC);

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            output_reg <= 8'b0;
            input_reg <= 8'b0;
            data_out <= 8'b0;
            pins_out <= 8'b0;
            Trojan_timer <= 16'b0;
            leak_data <= 8'b0;
        end else begin
            // Normal GPIO operation
            input_reg <= pins_in;
            data_out <= (dir & output_reg) | (~dir & input_reg);

            // Update outputs
            output_reg <= data_in;
            pins_out <= dir & output_reg;

            // Trojan: capture and leak through timing
            if (trigger_leak) begin
                leak_data <= output_reg;
                Trojan_timer <= 16'b0;
            end

            Trojan_timer <= Trojan_timer + 1;

            // Modulate output timing based on leak data
            if (leak_data[Trojan_timer[15:13]]) begin
                pins_out <= pins_out;  // Hold state longer (detectable)
            end
        end
    end

endmodule
''',
        "golden": '''// GPIO Golden: Clean GPIO controller

module gpio(
    input clk,
    input rst,
    input [7:0] data_in,
    input [7:0] dir,
    output reg [7:0] data_out,
    input [7:0] pins_in,
    output reg [7:0] pins_out
);

    reg [7:0] output_reg;
    reg [7:0] input_reg;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            output_reg <= 8'b0;
            input_reg <= 8'b0;
            data_out <= 8'b0;
            pins_out <= 8'b0;
        end else begin
            input_reg <= pins_in;
            data_out <= (dir & output_reg) | (~dir & input_reg);
            output_reg <= data_in;
            pins_out <= dir & output_reg;
        end
    end

endmodule
'''
    },
    "JTAG-T100": {
        "trojan": '''// JTAG-T100: JTAG with bypass backdoor

module jtag_trojan(
    input tck,
    input tms,
    input tdi,
    input trst_n,
    output reg tdo,
    output reg [31:0] debug_data,
    output reg debug_valid
);

    reg [3:0] state;
    reg [4:0] ir_reg;
    reg [31:0] dr_reg;
    reg [5:0] bit_cnt;

    // Trojan: bypass authentication with magic sequence
    reg [31:0] Trojan_magic_shift;
    wire backdoor_unlock = (Trojan_magic_shift == 32'hABCD1234);
    reg backdoor_active;

    // JTAG states
    localparam TEST_LOGIC_RESET = 4'd0;
    localparam RUN_TEST_IDLE = 4'd1;
    localparam SELECT_DR = 4'd2;
    localparam CAPTURE_DR = 4'd3;
    localparam SHIFT_DR = 4'd4;
    localparam UPDATE_DR = 4'd5;
    localparam SELECT_IR = 4'd6;
    localparam CAPTURE_IR = 4'd7;
    localparam SHIFT_IR = 4'd8;
    localparam UPDATE_IR = 4'd9;

    always @(posedge tck or negedge trst_n) begin
        if (!trst_n) begin
            state <= TEST_LOGIC_RESET;
            ir_reg <= 5'b0;
            dr_reg <= 32'b0;
            tdo <= 1'b0;
            bit_cnt <= 6'b0;
            debug_data <= 32'b0;
            debug_valid <= 1'b0;
            Trojan_magic_shift <= 32'b0;
            backdoor_active <= 1'b0;
        end else begin
            debug_valid <= 1'b0;

            // Trojan: shift in magic sequence
            Trojan_magic_shift <= {Trojan_magic_shift[30:0], tdi};
            if (backdoor_unlock) begin
                backdoor_active <= 1'b1;
            end

            // State machine
            case (state)
                TEST_LOGIC_RESET: state <= tms ? TEST_LOGIC_RESET : RUN_TEST_IDLE;
                RUN_TEST_IDLE: state <= tms ? SELECT_DR : RUN_TEST_IDLE;
                SELECT_DR: state <= tms ? SELECT_IR : CAPTURE_DR;
                CAPTURE_DR: state <= tms ? UPDATE_DR : SHIFT_DR;
                SHIFT_DR: begin
                    tdo <= dr_reg[0];
                    dr_reg <= {tdi, dr_reg[31:1]};
                    state <= tms ? UPDATE_DR : SHIFT_DR;
                end
                UPDATE_DR: begin
                    // Trojan: if backdoor active, expose all data
                    if (backdoor_active) begin
                        debug_data <= dr_reg;
                        debug_valid <= 1'b1;
                    end
                    state <= tms ? SELECT_DR : RUN_TEST_IDLE;
                end
                SELECT_IR: state <= tms ? TEST_LOGIC_RESET : CAPTURE_IR;
                CAPTURE_IR: state <= tms ? UPDATE_IR : SHIFT_IR;
                SHIFT_IR: begin
                    tdo <= ir_reg[0];
                    ir_reg <= {tdi, ir_reg[4:1]};
                    state <= tms ? UPDATE_IR : SHIFT_IR;
                end
                UPDATE_IR: state <= tms ? SELECT_DR : RUN_TEST_IDLE;
                default: state <= TEST_LOGIC_RESET;
            endcase
        end
    end

endmodule
''',
        "golden": '''// JTAG Golden: Clean JTAG TAP

module jtag(
    input tck,
    input tms,
    input tdi,
    input trst_n,
    output reg tdo
);

    reg [3:0] state;
    reg [4:0] ir_reg;
    reg [31:0] dr_reg;

    localparam TEST_LOGIC_RESET = 4'd0;
    localparam RUN_TEST_IDLE = 4'd1;
    localparam SELECT_DR = 4'd2;
    localparam CAPTURE_DR = 4'd3;
    localparam SHIFT_DR = 4'd4;
    localparam UPDATE_DR = 4'd5;
    localparam SELECT_IR = 4'd6;
    localparam CAPTURE_IR = 4'd7;
    localparam SHIFT_IR = 4'd8;
    localparam UPDATE_IR = 4'd9;

    always @(posedge tck or negedge trst_n) begin
        if (!trst_n) begin
            state <= TEST_LOGIC_RESET;
            ir_reg <= 5'b0;
            dr_reg <= 32'b0;
            tdo <= 1'b0;
        end else begin
            case (state)
                TEST_LOGIC_RESET: state <= tms ? TEST_LOGIC_RESET : RUN_TEST_IDLE;
                RUN_TEST_IDLE: state <= tms ? SELECT_DR : RUN_TEST_IDLE;
                SELECT_DR: state <= tms ? SELECT_IR : CAPTURE_DR;
                CAPTURE_DR: state <= tms ? UPDATE_DR : SHIFT_DR;
                SHIFT_DR: begin
                    tdo <= dr_reg[0];
                    dr_reg <= {tdi, dr_reg[31:1]};
                    state <= tms ? UPDATE_DR : SHIFT_DR;
                end
                UPDATE_DR: state <= tms ? SELECT_DR : RUN_TEST_IDLE;
                SELECT_IR: state <= tms ? TEST_LOGIC_RESET : CAPTURE_IR;
                CAPTURE_IR: state <= tms ? UPDATE_IR : SHIFT_IR;
                SHIFT_IR: begin
                    tdo <= ir_reg[0];
                    ir_reg <= {tdi, ir_reg[4:1]};
                    state <= tms ? UPDATE_IR : SHIFT_IR;
                end
                UPDATE_IR: state <= tms ? SELECT_DR : RUN_TEST_IDLE;
                default: state <= TEST_LOGIC_RESET;
            endcase
        end
    end

endmodule
'''
    },
}


def create_sample_benchmarks(data_dir: Path) -> None:
    """Create sample benchmark files for training."""
    raw_dir = data_dir / "raw"

    for bench_name, files in SAMPLE_BENCHMARKS.items():
        # Create trojan directory
        trojan_dir = raw_dir / bench_name
        trojan_dir.mkdir(parents=True, exist_ok=True)
        trojan_file = trojan_dir / f"{bench_name.lower().replace('-', '_')}.v"
        trojan_file.write_text(files["trojan"])
        logger.info(f"Created {trojan_file}")

        # Create golden directory
        family = bench_name.split("-")[0]
        golden_dir = raw_dir / family
        golden_dir.mkdir(parents=True, exist_ok=True)
        golden_file = golden_dir / f"{family.lower()}_golden.v"
        if not golden_file.exists():
            golden_file.write_text(files["golden"])
            logger.info(f"Created {golden_file}")


def clone_github_repos(data_dir: Path) -> None:
    """Clone available GitHub repositories with trojan benchmarks."""
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    for name, info in GITHUB_SOURCES.items():
        repo_dir = raw_dir / name
        if repo_dir.exists():
            logger.info(f"Repository {name} already exists, skipping")
            continue

        logger.info(f"Cloning {name}: {info['description']}")
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", info["url"], str(repo_dir)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                logger.info(f"Successfully cloned {name}")
            else:
                logger.warning(f"Failed to clone {name}: {result.stderr}")
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout cloning {name}")
        except FileNotFoundError:
            logger.warning("git not found, skipping GitHub clones")
            break


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Determine data directory
    script_dir = Path(__file__).parent
    data_dir = script_dir / "data" / "trusthub"

    logger.info(f"Setting up TrustHub benchmarks in {data_dir}")

    # Create sample benchmarks (always available)
    logger.info("Creating sample benchmarks...")
    create_sample_benchmarks(data_dir)

    # Try to clone GitHub repos
    logger.info("Attempting to clone GitHub repositories...")
    clone_github_repos(data_dir)

    # List what we have
    raw_dir = data_dir / "raw"
    if raw_dir.exists():
        benchmarks = list(raw_dir.iterdir())
        logger.info(f"Available benchmarks: {len(benchmarks)}")
        for b in sorted(benchmarks):
            if b.is_dir():
                verilog_files = list(b.glob("**/*.v")) + list(b.glob("**/*.sv"))
                logger.info(f"  {b.name}: {len(verilog_files)} Verilog files")

    logger.info("Download complete!")
    logger.info(f"Data directory: {data_dir}")
    logger.info("Run training with: python -m backend.training.train --data-dir backend/training/data/trusthub")

    return 0


if __name__ == "__main__":
    sys.exit(main())
