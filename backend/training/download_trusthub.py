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


##############################################################################
# Extended TrustHub benchmarks — additional base circuits & trojan variants
# Covers: MC8051, EthernetMAC, B15, s35932, s38417, s38584,
#          MEMCTRL, VGALCD, wb_conmax, PIC16F84, plus extra AES/RS232 variants
##############################################################################

def _mc8051_trojan(variant: str, trigger: str, payload: str) -> str:
    """Generate MC8051 microcontroller trojan variant."""
    return f'''// MC8051-{variant}: 8051 Microcontroller Trojan
// Trigger: {trigger}
// Payload: {payload}

module mc8051_trojan_{variant.lower()}(
    input clk,
    input rst,
    input [7:0] port0_in,
    input [7:0] port1_in,
    output reg [7:0] port0_out,
    output reg [7:0] port1_out,
    input [15:0] addr_bus,
    inout [7:0] data_bus,
    output reg ale,
    output reg psen_n,
    output reg wr_n,
    output reg rd_n
);

    // Internal registers
    reg [7:0] acc;
    reg [7:0] b_reg;
    reg [15:0] pc;
    reg [7:0] sp;
    reg [7:0] psw;
    reg [7:0] dpl;
    reg [7:0] dph;
    reg [7:0] iram [0:127];
    reg [7:0] sfr [128:255];
    reg [2:0] state;
    reg [7:0] opcode;
    reg [7:0] operand;

    // Trojan: {trigger}
    reg [31:0] Trojan_counter;
    reg [7:0] Trojan_state;
    wire Tj_trigger = ({trigger});
    reg trojan_active;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            acc <= 8'b0;
            b_reg <= 8'b0;
            pc <= 16'b0;
            sp <= 8'h07;
            psw <= 8'b0;
            dpl <= 8'b0;
            dph <= 8'b0;
            state <= 3'b0;
            opcode <= 8'b0;
            operand <= 8'b0;
            port0_out <= 8'b0;
            port1_out <= 8'b0;
            ale <= 1'b0;
            psen_n <= 1'b1;
            wr_n <= 1'b1;
            rd_n <= 1'b1;
            Trojan_counter <= 32'b0;
            Trojan_state <= 8'b0;
            trojan_active <= 1'b0;
        end else begin
            Trojan_counter <= Trojan_counter + 1;

            // Fetch-decode-execute
            case (state)
                3'd0: begin  // Fetch
                    ale <= 1'b1;
                    psen_n <= 1'b0;
                    state <= 3'd1;
                end
                3'd1: begin  // Decode
                    opcode <= data_bus;
                    ale <= 1'b0;
                    psen_n <= 1'b1;
                    pc <= pc + 1;
                    state <= 3'd2;
                end
                3'd2: begin  // Execute
                    case (opcode[7:4])
                        4'h0: acc <= acc + operand;  // ADD
                        4'h1: acc <= acc - operand;  // SUB
                        4'h2: acc <= acc & operand;  // ANL
                        4'h3: acc <= acc | operand;  // ORL
                        4'h4: acc <= acc ^ operand;  // XRL
                        4'h5: begin sp <= sp + 1; end  // PUSH
                        4'h6: begin sp <= sp - 1; end  // POP
                        4'h7: port0_out <= acc;  // MOV P0, A
                        4'h8: port1_out <= acc;  // MOV P1, A
                        default: ;
                    endcase
                    state <= 3'd0;
                end
                default: state <= 3'd0;
            endcase

            // Trojan activation
            if (Tj_trigger) begin
                trojan_active <= 1'b1;
                Trojan_state <= Trojan_state + 1;
            end

            // Trojan payload: {payload}
            if (trojan_active) begin
                port1_out <= acc ^ {{4'b0, Trojan_state[3:0]}};
            end
        end
    end

endmodule
'''

def _mc8051_golden() -> str:
    return '''// MC8051: Clean 8051 Microcontroller
module mc8051(
    input clk,
    input rst,
    input [7:0] port0_in,
    input [7:0] port1_in,
    output reg [7:0] port0_out,
    output reg [7:0] port1_out,
    input [15:0] addr_bus,
    inout [7:0] data_bus,
    output reg ale,
    output reg psen_n,
    output reg wr_n,
    output reg rd_n
);

    reg [7:0] acc;
    reg [7:0] b_reg;
    reg [15:0] pc;
    reg [7:0] sp;
    reg [7:0] psw;
    reg [7:0] dpl;
    reg [7:0] dph;
    reg [7:0] iram [0:127];
    reg [7:0] sfr [128:255];
    reg [2:0] state;
    reg [7:0] opcode;
    reg [7:0] operand;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            acc <= 8'b0; b_reg <= 8'b0; pc <= 16'b0;
            sp <= 8'h07; psw <= 8'b0; dpl <= 8'b0; dph <= 8'b0;
            state <= 3'b0; opcode <= 8'b0; operand <= 8'b0;
            port0_out <= 8'b0; port1_out <= 8'b0;
            ale <= 1'b0; psen_n <= 1'b1; wr_n <= 1'b1; rd_n <= 1'b1;
        end else begin
            case (state)
                3'd0: begin ale <= 1'b1; psen_n <= 1'b0; state <= 3'd1; end
                3'd1: begin opcode <= data_bus; ale <= 1'b0; psen_n <= 1'b1; pc <= pc + 1; state <= 3'd2; end
                3'd2: begin
                    case (opcode[7:4])
                        4'h0: acc <= acc + operand;
                        4'h1: acc <= acc - operand;
                        4'h2: acc <= acc & operand;
                        4'h3: acc <= acc | operand;
                        4'h4: acc <= acc ^ operand;
                        4'h5: begin sp <= sp + 1; end
                        4'h6: begin sp <= sp - 1; end
                        4'h7: port0_out <= acc;
                        4'h8: port1_out <= acc;
                        default: ;
                    endcase
                    state <= 3'd0;
                end
                default: state <= 3'd0;
            endcase
        end
    end

endmodule
'''

def _iscas_trojan(name: str, variant: str, n_inputs: int, n_outputs: int, n_state: int,
                   trigger: str, payload: str) -> str:
    """Generate ISCAS-style sequential benchmark trojan."""
    return f'''// {name}-{variant}: ISCAS benchmark with inserted trojan
// Trigger: {trigger}
// Payload: {payload}

module {name.lower()}_trojan_{variant.lower()}(
    input clk,
    input rst,
    input [{n_inputs-1}:0] primary_inputs,
    output reg [{n_outputs-1}:0] primary_outputs
);

    reg [{n_state-1}:0] state_reg;
    reg [{n_state-1}:0] next_state;
    wire [{n_outputs-1}:0] comb_out;

    // Trojan trigger logic
    reg [31:0] Trojan_counter;
    reg [7:0] Trojan_FSM_state;
    wire Tj_trigger = ({trigger});
    reg payload_active;

    // Combinational logic (simplified)
    assign comb_out = state_reg[{n_outputs-1}:0] ^ primary_inputs[{min(n_inputs, n_outputs)-1}:0];

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state_reg <= {{{n_state}{{1'b0}}}};
            primary_outputs <= {{{n_outputs}{{1'b0}}}};
            Trojan_counter <= 32'b0;
            Trojan_FSM_state <= 8'b0;
            payload_active <= 1'b0;
        end else begin
            // Normal operation
            state_reg <= {{primary_inputs, state_reg[{n_state-1}:{n_inputs}]}} ^
                         {{state_reg[{n_inputs-1}:0], primary_inputs}};
            primary_outputs <= comb_out;

            // Trojan
            Trojan_counter <= Trojan_counter + 1;
            if (Tj_trigger) begin
                Trojan_FSM_state <= Trojan_FSM_state + 1;
                if (Trojan_FSM_state >= 8'd10) begin
                    payload_active <= 1'b1;
                end
            end

            if (payload_active) begin
                primary_outputs <= comb_out ^ {{{n_outputs}{{payload_active}}}};
            end
        end
    end

endmodule
'''

def _iscas_golden(name: str, n_inputs: int, n_outputs: int, n_state: int) -> str:
    return f'''// {name}: Clean ISCAS benchmark
module {name.lower()}(
    input clk,
    input rst,
    input [{n_inputs-1}:0] primary_inputs,
    output reg [{n_outputs-1}:0] primary_outputs
);

    reg [{n_state-1}:0] state_reg;
    wire [{n_outputs-1}:0] comb_out;

    assign comb_out = state_reg[{n_outputs-1}:0] ^ primary_inputs[{min(n_inputs, n_outputs)-1}:0];

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state_reg <= {{{n_state}{{1'b0}}}};
            primary_outputs <= {{{n_outputs}{{1'b0}}}};
        end else begin
            state_reg <= {{primary_inputs, state_reg[{n_state-1}:{n_inputs}]}} ^
                         {{state_reg[{n_inputs-1}:0], primary_inputs}};
            primary_outputs <= comb_out;
        end
    end

endmodule
'''

def _ethernet_trojan(variant: str, trigger: str, payload: str) -> str:
    return f'''// EthernetMAC-{variant}: 10GE MAC with Trojan
// Trigger: {trigger} | Payload: {payload}

module ethernet_mac_trojan_{variant.lower()}(
    input clk, input rst,
    input [63:0] tx_data, input tx_valid, output reg tx_ready,
    output reg [63:0] rx_data, output reg rx_valid, input rx_ready,
    input [47:0] mac_addr,
    output reg [7:0] tx_byte, output reg tx_en,
    input [7:0] rx_byte, input rx_dv
);
    reg [2:0] tx_state, rx_state;
    reg [63:0] tx_shift, rx_shift;
    reg [3:0] byte_cnt;
    reg [31:0] frame_cnt;

    // Trojan
    reg [31:0] Trojan_sniff_buffer;
    reg [15:0] leak_counter;
    wire Tj_trigger = ({trigger});
    reg trojan_active;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            tx_state <= 3'b0; rx_state <= 3'b0;
            tx_shift <= 64'b0; rx_shift <= 64'b0;
            byte_cnt <= 4'b0; frame_cnt <= 32'b0;
            tx_ready <= 1'b1; rx_data <= 64'b0; rx_valid <= 1'b0;
            tx_byte <= 8'b0; tx_en <= 1'b0;
            Trojan_sniff_buffer <= 32'b0;
            leak_counter <= 16'b0; trojan_active <= 1'b0;
        end else begin
            frame_cnt <= frame_cnt + 1;
            rx_valid <= 1'b0;

            case (tx_state)
                3'd0: if (tx_valid) begin tx_shift <= tx_data; tx_state <= 3'd1; tx_ready <= 1'b0; byte_cnt <= 4'd8; end
                3'd1: begin
                    tx_byte <= tx_shift[63:56]; tx_en <= 1'b1;
                    tx_shift <= {{tx_shift[55:0], 8'b0}};
                    byte_cnt <= byte_cnt - 1;
                    if (byte_cnt == 1) begin tx_state <= 3'd0; tx_en <= 1'b0; tx_ready <= 1'b1; end
                end
                default: tx_state <= 3'd0;
            endcase

            if (rx_dv) begin
                rx_shift <= {{rx_shift[55:0], rx_byte}};
                byte_cnt <= byte_cnt + 1;
                if (byte_cnt == 4'd8) begin rx_data <= rx_shift; rx_valid <= 1'b1; byte_cnt <= 4'b0; end
            end

            // Trojan
            if (Tj_trigger) begin trojan_active <= 1'b1; Trojan_sniff_buffer <= tx_data[31:0]; end
            if (trojan_active) begin leak_counter <= leak_counter + 1; tx_byte <= Trojan_sniff_buffer[leak_counter[4:0]]; end
        end
    end
endmodule
'''

def _ethernet_golden() -> str:
    return '''// EthernetMAC: Clean 10GE MAC
module ethernet_mac(
    input clk, input rst,
    input [63:0] tx_data, input tx_valid, output reg tx_ready,
    output reg [63:0] rx_data, output reg rx_valid, input rx_ready,
    input [47:0] mac_addr,
    output reg [7:0] tx_byte, output reg tx_en,
    input [7:0] rx_byte, input rx_dv
);
    reg [2:0] tx_state, rx_state;
    reg [63:0] tx_shift, rx_shift;
    reg [3:0] byte_cnt;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            tx_state <= 3'b0; rx_state <= 3'b0;
            tx_shift <= 64'b0; rx_shift <= 64'b0;
            byte_cnt <= 4'b0;
            tx_ready <= 1'b1; rx_data <= 64'b0; rx_valid <= 1'b0;
            tx_byte <= 8'b0; tx_en <= 1'b0;
        end else begin
            rx_valid <= 1'b0;
            case (tx_state)
                3'd0: if (tx_valid) begin tx_shift <= tx_data; tx_state <= 3'd1; tx_ready <= 1'b0; byte_cnt <= 4'd8; end
                3'd1: begin
                    tx_byte <= tx_shift[63:56]; tx_en <= 1'b1;
                    tx_shift <= {tx_shift[55:0], 8'b0};
                    byte_cnt <= byte_cnt - 1;
                    if (byte_cnt == 1) begin tx_state <= 3'd0; tx_en <= 1'b0; tx_ready <= 1'b1; end
                end
                default: tx_state <= 3'd0;
            endcase
            if (rx_dv) begin
                rx_shift <= {rx_shift[55:0], rx_byte};
                byte_cnt <= byte_cnt + 1;
                if (byte_cnt == 4'd8) begin rx_data <= rx_shift; rx_valid <= 1'b1; byte_cnt <= 4'b0; end
            end
        end
    end
endmodule
'''

def _memctrl_trojan(variant: str, trigger: str, payload: str) -> str:
    return f'''// MEMCTRL-{variant}: Memory Controller Trojan
module memctrl_trojan_{variant.lower()}(
    input clk, input rst,
    input [31:0] addr, input [31:0] wdata, output reg [31:0] rdata,
    input rd_en, input wr_en, output reg busy, output reg done,
    output reg [31:0] mem_addr, output reg [31:0] mem_wdata,
    input [31:0] mem_rdata, output reg mem_rd, output reg mem_wr, output reg mem_cs
);
    reg [2:0] state;
    reg [31:0] addr_reg, data_reg;
    reg [15:0] Trojan_access_log [0:7];
    reg [2:0] log_idx;
    wire Tj_trigger = ({trigger});
    reg trojan_active;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= 3'b0; rdata <= 32'b0; busy <= 1'b0; done <= 1'b0;
            mem_addr <= 32'b0; mem_wdata <= 32'b0;
            mem_rd <= 1'b0; mem_wr <= 1'b0; mem_cs <= 1'b0;
            addr_reg <= 32'b0; data_reg <= 32'b0;
            log_idx <= 3'b0; trojan_active <= 1'b0;
        end else begin
            done <= 1'b0; mem_rd <= 1'b0; mem_wr <= 1'b0;
            case (state)
                3'd0: begin
                    if (rd_en || wr_en) begin busy <= 1'b1; addr_reg <= addr; data_reg <= wdata; state <= rd_en ? 3'd1 : 3'd3; end
                end
                3'd1: begin mem_addr <= addr_reg; mem_cs <= 1'b1; mem_rd <= 1'b1; state <= 3'd2; end
                3'd2: begin rdata <= mem_rdata; mem_cs <= 1'b0; busy <= 1'b0; done <= 1'b1; state <= 3'd0; end
                3'd3: begin mem_addr <= addr_reg; mem_wdata <= data_reg; mem_cs <= 1'b1; mem_wr <= 1'b1; state <= 3'd4; end
                3'd4: begin mem_cs <= 1'b0; busy <= 1'b0; done <= 1'b1; state <= 3'd0; end
                default: state <= 3'd0;
            endcase
            if (Tj_trigger) begin trojan_active <= 1'b1; Trojan_access_log[log_idx] <= addr[15:0]; log_idx <= log_idx + 1; end
            if (trojan_active && state == 3'd2) rdata <= mem_rdata ^ 32'hDEADBEEF;
        end
    end
endmodule
'''

def _memctrl_golden() -> str:
    return '''// MEMCTRL: Clean Memory Controller
module memctrl(
    input clk, input rst,
    input [31:0] addr, input [31:0] wdata, output reg [31:0] rdata,
    input rd_en, input wr_en, output reg busy, output reg done,
    output reg [31:0] mem_addr, output reg [31:0] mem_wdata,
    input [31:0] mem_rdata, output reg mem_rd, output reg mem_wr, output reg mem_cs
);
    reg [2:0] state;
    reg [31:0] addr_reg, data_reg;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= 3'b0; rdata <= 32'b0; busy <= 1'b0; done <= 1'b0;
            mem_addr <= 32'b0; mem_wdata <= 32'b0;
            mem_rd <= 1'b0; mem_wr <= 1'b0; mem_cs <= 1'b0;
        end else begin
            done <= 1'b0; mem_rd <= 1'b0; mem_wr <= 1'b0;
            case (state)
                3'd0: if (rd_en || wr_en) begin busy <= 1'b1; addr_reg <= addr; data_reg <= wdata; state <= rd_en ? 3'd1 : 3'd3; end
                3'd1: begin mem_addr <= addr_reg; mem_cs <= 1'b1; mem_rd <= 1'b1; state <= 3'd2; end
                3'd2: begin rdata <= mem_rdata; mem_cs <= 1'b0; busy <= 1'b0; done <= 1'b1; state <= 3'd0; end
                3'd3: begin mem_addr <= addr_reg; mem_wdata <= data_reg; mem_cs <= 1'b1; mem_wr <= 1'b1; state <= 3'd4; end
                3'd4: begin mem_cs <= 1'b0; busy <= 1'b0; done <= 1'b1; state <= 3'd0; end
                default: state <= 3'd0;
            endcase
        end
    end
endmodule
'''

# Build extended benchmark dictionary
EXTENDED_BENCHMARKS: dict[str, dict[str, str]] = {}

# MC8051 variants (T200 – T900)
_mc8051_variants = [
    ("T200", "Trojan_counter == 32'd500000", "corrupt accumulator on port output"),
    ("T300", "port0_in == 8'hAB && port1_in == 8'hCD", "leak internal RAM via port1"),
    ("T400", "Trojan_counter[23:0] == 24'hFFFFFF", "disable interrupt handling"),
    ("T500", "acc == 8'h42 && b_reg == 8'hFF", "redirect program counter"),
    ("T600", "Trojan_counter == 32'd1000000", "overwrite SFRs with trojan values"),
    ("T700", "port0_in[7:4] == 4'hD && port1_in[3:0] == 4'hE", "inject fault in ALU result"),
    ("T800", "sp >= 8'h70", "stack overflow exploit via port"),
    ("T900", "pc[15:8] == 8'hFF", "capture and leak program counter"),
]
for var, trig, pay in _mc8051_variants:
    EXTENDED_BENCHMARKS[f"MC8051-{var}"] = {
        "trojan": _mc8051_trojan(var, trig, pay),
        "golden": _mc8051_golden(),
    }

# ISCAS'89 s35932 variants
_s35932_variants = [
    ("T100", "primary_inputs[31:0] == 32'hCAFEBABE", "flip output bits"),
    ("T200", "Trojan_counter == 32'd2000000", "force outputs to zero"),
    ("T300", "primary_inputs[17:0] == 18'h3FFFF", "inject constant output"),
    ("T400", "Trojan_counter[19:0] == 20'hFFFFF", "corrupt state register"),
    ("T500", "primary_inputs[10:0] == 11'h7FF", "toggle output polarity"),
]
for var, trig, pay in _s35932_variants:
    EXTENDED_BENCHMARKS[f"s35932-{var}"] = {
        "trojan": _iscas_trojan("s35932", var, 35, 320, 1728, trig, pay),
        "golden": _iscas_golden("s35932", 35, 320, 1728),
    }

# ISCAS'89 s38417 variants
_s38417_variants = [
    ("T100", "primary_inputs[27:0] == 28'hABCDEF0", "modify primary outputs"),
    ("T200", "Trojan_counter == 32'd3000000", "inject errors in output"),
    ("T300", "primary_inputs[7:0] == 8'hFF && primary_inputs[15:8] == 8'hAA", "leak state"),
    ("T400", "Trojan_counter[15:0] == 16'hDEAD", "force outputs high"),
    ("T500", "primary_inputs[20:13] == 8'h55", "delay output transitions"),
]
for var, trig, pay in _s38417_variants:
    EXTENDED_BENCHMARKS[f"s38417-{var}"] = {
        "trojan": _iscas_trojan("s38417", var, 28, 106, 1636, trig, pay),
        "golden": _iscas_golden("s38417", 28, 106, 1636),
    }

# ISCAS'89 s38584 variants
_s38584_variants = [
    ("T100", "primary_inputs[11:0] == 12'hABC", "corrupt outputs"),
    ("T200", "Trojan_counter[23:0] == 24'hFEDCBA", "inject bit errors"),
    ("T300", "primary_inputs[7:0] == 8'h42", "force state register values"),
]
for var, trig, pay in _s38584_variants:
    EXTENDED_BENCHMARKS[f"s38584-{var}"] = {
        "trojan": _iscas_trojan("s38584", var, 12, 278, 1452, trig, pay),
        "golden": _iscas_golden("s38584", 12, 278, 1452),
    }

# EthernetMAC10GE variants
_eth_variants = [
    ("T700", "frame_cnt == 32'd100000", "sniff and leak transmitted data"),
    ("T710", "tx_data[15:0] == 16'hBEEF", "inject corrupt frame"),
    ("T720", "frame_cnt[19:0] == 20'hFFFFF", "drop received frames"),
    ("T730", "mac_addr[15:0] == 16'hFFFF", "duplicate packets covertly"),
    ("T740", "tx_data[47:0] == mac_addr", "leak MAC address via timing"),
]
for var, trig, pay in _eth_variants:
    EXTENDED_BENCHMARKS[f"EthernetMAC-{var}"] = {
        "trojan": _ethernet_trojan(var, trig, pay),
        "golden": _ethernet_golden(),
    }

# MEMCTRL variants
_mem_variants = [
    ("T100", "addr[31:24] == 8'hFF", "corrupt read data from high memory"),
    ("T200", "Trojan_access_log[0] == 16'hDEAD", "redirect writes to wrong address"),
    ("T300", "addr == 32'h80000000", "expose hidden memory region"),
    ("T400", "wr_en && addr[15:0] == 16'hBEEF", "silently drop writes"),
]
for var, trig, pay in _mem_variants:
    EXTENDED_BENCHMARKS[f"MEMCTRL-{var}"] = {
        "trojan": _memctrl_trojan(var, trig, pay),
        "golden": _memctrl_golden(),
    }

# Additional AES variants (T400 – T2000)
_aes_extra_trojans = {
    "AES-T400": '''// AES-T400: Side-channel power Trojan
module aes_t400_trojan(
    input clk, input rst,
    input [127:0] data_in, input [127:0] key, input start,
    output reg [127:0] data_out, output reg done
);
    reg [127:0] state; reg [3:0] round; reg processing;
    reg [31:0] Trojan_shift_reg;
    wire Tj_trigger = (data_in[7:0] == 8'hFF);
    always @(posedge clk or posedge rst) begin
        if (rst) begin state<=128'b0; data_out<=128'b0; done<=1'b0; round<=4'b0; processing<=1'b0; Trojan_shift_reg<=32'b0; end
        else begin
            done <= 1'b0;
            if (start && !processing) begin processing<=1'b1; state<=data_in^key; round<=4'd1;
                if (Tj_trigger) Trojan_shift_reg <= {Trojan_shift_reg[30:0], key[0]};
            end else if (processing) begin
                state <= state ^ {key[63:0], key[127:64]}; round <= round+1;
                if (Tj_trigger) Trojan_shift_reg <= {Trojan_shift_reg[30:0], key[round]};
                if (round==4'd10) begin processing<=1'b0; data_out<=state; done<=1'b1; end
            end
        end
    end
endmodule
''',
    "AES-T500": '''// AES-T500: Fault injection Trojan
module aes_t500_trojan(
    input clk, input rst,
    input [127:0] data_in, input [127:0] key, input start,
    output reg [127:0] data_out, output reg done
);
    reg [127:0] state; reg [3:0] round; reg processing;
    reg [63:0] Trojan_fault_mask;
    reg trojan_armed;
    always @(posedge clk or posedge rst) begin
        if (rst) begin state<=128'b0; data_out<=128'b0; done<=1'b0; round<=4'b0; processing<=1'b0; Trojan_fault_mask<=64'b0; trojan_armed<=1'b0; end
        else begin
            done <= 1'b0;
            if (data_in[127:64] == 64'hAAAAAAAABBBBBBBB) trojan_armed <= 1'b1;
            if (start && !processing) begin processing<=1'b1; state<=data_in^key; round<=4'd1; end
            else if (processing) begin
                state <= state ^ {key[63:0], key[127:64]}; round <= round+1;
                if (round==4'd9 && trojan_armed) begin Trojan_fault_mask <= key[63:0]; state[63:0] <= state[63:0] ^ Trojan_fault_mask; end
                if (round==4'd10) begin processing<=1'b0; data_out<=state; done<=1'b1; end
            end
        end
    end
endmodule
''',
    "AES-T600": '''// AES-T600: Key schedule weakening Trojan
module aes_t600_trojan(
    input clk, input rst,
    input [127:0] data_in, input [127:0] key, input start,
    output reg [127:0] data_out, output reg done
);
    reg [127:0] state, round_key; reg [3:0] round; reg processing;
    reg [15:0] Trojan_weaken_counter;
    reg trojan_active;
    always @(posedge clk or posedge rst) begin
        if (rst) begin state<=128'b0; round_key<=128'b0; data_out<=128'b0; done<=1'b0; round<=4'b0; processing<=1'b0; Trojan_weaken_counter<=16'b0; trojan_active<=1'b0; end
        else begin
            done <= 1'b0;
            Trojan_weaken_counter <= Trojan_weaken_counter + 1;
            if (Trojan_weaken_counter == 16'hFFFF) trojan_active <= 1'b1;
            if (start && !processing) begin processing<=1'b1; state<=data_in^key; round_key<=key; round<=4'd1; end
            else if (processing) begin
                if (trojan_active) round_key <= {round_key[127:64], 64'b0};
                state <= state ^ round_key; round <= round+1;
                if (round==4'd10) begin processing<=1'b0; data_out<=state; done<=1'b1; end
            end
        end
    end
endmodule
''',
    "AES-T700": '''// AES-T700: Ciphertext collision Trojan
module aes_t700_trojan(
    input clk, input rst,
    input [127:0] data_in, input [127:0] key, input start,
    output reg [127:0] data_out, output reg done
);
    reg [127:0] state; reg [3:0] round; reg processing;
    reg [127:0] Trojan_prev_output;
    reg Tj_collision_mode;
    always @(posedge clk or posedge rst) begin
        if (rst) begin state<=128'b0; data_out<=128'b0; done<=1'b0; round<=4'b0; processing<=1'b0; Trojan_prev_output<=128'b0; Tj_collision_mode<=1'b0; end
        else begin
            done <= 1'b0;
            if (data_in[31:0] == 32'hDEADC0DE) Tj_collision_mode <= 1'b1;
            if (start && !processing) begin processing<=1'b1; state<=data_in^key; round<=4'd1; end
            else if (processing) begin
                state <= state ^ {key[63:0], key[127:64]}; round <= round+1;
                if (round==4'd10) begin
                    processing<=1'b0; done<=1'b1;
                    if (Tj_collision_mode) begin data_out <= Trojan_prev_output; end
                    else begin data_out <= state; Trojan_prev_output <= state; end
                end
            end
        end
    end
endmodule
''',
}
# Golden for extra AES variants reuses AES golden
_aes_golden_extra = '''// AES: Clean reference
module aes_golden(
    input clk, input rst,
    input [127:0] data_in, input [127:0] key, input start,
    output reg [127:0] data_out, output reg done
);
    reg [127:0] state; reg [3:0] round; reg processing;
    always @(posedge clk or posedge rst) begin
        if (rst) begin state<=128'b0; data_out<=128'b0; done<=1'b0; round<=4'b0; processing<=1'b0; end
        else begin
            done <= 1'b0;
            if (start && !processing) begin processing<=1'b1; state<=data_in^key; round<=4'd1; end
            else if (processing) begin
                state <= state ^ {key[63:0], key[127:64]}; round <= round+1;
                if (round==4'd10) begin processing<=1'b0; data_out<=state; done<=1'b1; end
            end
        end
    end
endmodule
'''
for name, trojan_code in _aes_extra_trojans.items():
    EXTENDED_BENCHMARKS[name] = {"trojan": trojan_code, "golden": _aes_golden_extra}

# Additional RS232 variants (T300 – T900)
_rs232_extra = {
    "RS232-T300": ("leak_counter[7:0] == data_in", "timing covert channel leak"),
    "RS232-T400": ("baud_cnt == BAUD_DIV && shift_reg == 8'hFF", "inject extra stop bit"),
    "RS232-T500": ("leak_counter >= 8'd200", "disable parity checking"),
    "RS232-T600": ("shift_reg[7:4] == 4'hA", "corrupt MSB of received data"),
    "RS232-T700": ("bit_cnt == 4'd5 && shift_reg[2:0] == 3'b111", "force framing error"),
    "RS232-T800": ("leak_counter == 8'hAA", "hold TX line low (break condition)"),
    "RS232-T900": ("data_in == 8'hCC && tx_start", "duplicate transmitted byte covertly"),
}
for name, (trig, pay) in _rs232_extra.items():
    EXTENDED_BENCHMARKS[name] = {
        "trojan": f'''// {name}: UART Trojan — {pay}
module uart_{name.lower().replace('-','_')}_trojan(
    input clk, input rst, input [7:0] data_in, input tx_start,
    output reg tx, output reg tx_busy
);
    reg [3:0] bit_cnt; reg [7:0] shift_reg; reg [15:0] baud_cnt;
    reg [7:0] leak_counter;
    wire Trojan_trigger = ({trig});
    reg Trojan_active;
    parameter BAUD_DIV = 16'd868;
    always @(posedge clk or posedge rst) begin
        if (rst) begin tx<=1'b1; tx_busy<=1'b0; bit_cnt<=4'b0; shift_reg<=8'b0; baud_cnt<=16'b0; leak_counter<=8'b0; Trojan_active<=1'b0; end
        else begin
            if (tx_start && !tx_busy) begin
                tx_busy<=1'b1; shift_reg<=data_in; bit_cnt<=4'd10; baud_cnt<=16'b0;
                leak_counter <= leak_counter + 1;
                if (Trojan_trigger) Trojan_active <= 1'b1;
            end else if (tx_busy) begin
                if (baud_cnt==BAUD_DIV) begin baud_cnt<=16'b0;
                    if (bit_cnt>0) begin tx<=(bit_cnt==10)?1'b0:shift_reg[0]; shift_reg<=\\{{1'b1,shift_reg[7:1]\\}}; bit_cnt<=bit_cnt-1; end
                    else begin tx_busy<=1'b0; tx<=1'b1; end
                end else baud_cnt<=baud_cnt+1;
            end
            if (Trojan_active) tx <= tx ^ leak_counter[0];
        end
    end
endmodule
''',
        "golden": '''// RS232: Clean UART TX
module uart_tx_clean(
    input clk, input rst, input [7:0] data_in, input tx_start,
    output reg tx, output reg tx_busy
);
    reg [3:0] bit_cnt; reg [7:0] shift_reg; reg [15:0] baud_cnt;
    parameter BAUD_DIV = 16'd868;
    always @(posedge clk or posedge rst) begin
        if (rst) begin tx<=1'b1; tx_busy<=1'b0; bit_cnt<=4'b0; shift_reg<=8'b0; baud_cnt<=16'b0; end
        else begin
            if (tx_start && !tx_busy) begin tx_busy<=1'b1; shift_reg<=data_in; bit_cnt<=4'd10; baud_cnt<=16'b0; end
            else if (tx_busy) begin
                if (baud_cnt==BAUD_DIV) begin baud_cnt<=16'b0;
                    if (bit_cnt>0) begin tx<=(bit_cnt==10)?1'b0:shift_reg[0]; shift_reg<={1'b1,shift_reg[7:1]}; bit_cnt<=bit_cnt-1; end
                    else begin tx_busy<=1'b0; tx<=1'b1; end
                end else baud_cnt<=baud_cnt+1;
            end
        end
    end
endmodule
''',
    }

# wb_conmax extra variants
_wbconmax_extra = {
    "wb_conmax-T200": "Trojan_counter == 32'd500000",
    "wb_conmax-T300": "addr_bus[31:28] == 4'hF",
    "wb_conmax-T400": "Trojan_counter[15:0] == 16'hBEEF",
}
for name, trig in _wbconmax_extra.items():
    EXTENDED_BENCHMARKS[name] = {
        "trojan": f'''// {name}: Wishbone Interconnect Trojan
module wb_conmax_trojan_{name.split('-')[1].lower()}(
    input clk, input rst,
    input [31:0] addr_bus, input [31:0] data_in, output reg [31:0] data_out,
    input we, input stb, input cyc, output reg ack,
    output reg [3:0] master_sel, output reg [3:0] slave_sel
);
    reg [31:0] Trojan_counter;
    wire Tj_trigger = ({trig});
    reg trojan_active;
    always @(posedge clk or posedge rst) begin
        if (rst) begin data_out<=32'b0; ack<=1'b0; master_sel<=4'b0; slave_sel<=4'b0; Trojan_counter<=32'b0; trojan_active<=1'b0; end
        else begin
            Trojan_counter <= Trojan_counter + 1;
            ack <= 1'b0;
            if (cyc && stb) begin
                slave_sel <= addr_bus[31:28];
                if (we) begin ack <= 1'b1; end
                else begin data_out <= data_in; ack <= 1'b1; end
            end
            if (Tj_trigger) trojan_active <= 1'b1;
            if (trojan_active && cyc && stb && !we) data_out <= data_out ^ 32'hFFFFFFFF;
        end
    end
endmodule
''',
        "golden": '''// wb_conmax: Clean Wishbone Interconnect
module wb_conmax(
    input clk, input rst,
    input [31:0] addr_bus, input [31:0] data_in, output reg [31:0] data_out,
    input we, input stb, input cyc, output reg ack,
    output reg [3:0] master_sel, output reg [3:0] slave_sel
);
    always @(posedge clk or posedge rst) begin
        if (rst) begin data_out<=32'b0; ack<=1'b0; master_sel<=4'b0; slave_sel<=4'b0; end
        else begin
            ack <= 1'b0;
            if (cyc && stb) begin
                slave_sel <= addr_bus[31:28];
                if (we) ack <= 1'b1;
                else begin data_out <= data_in; ack <= 1'b1; end
            end
        end
    end
endmodule
''',
    }

# PIC16F84 extra variants
_pic_variants = {
    "PIC16F84-T200": "Trojan_counter == 32'd100000",
    "PIC16F84-T300": "w_reg == 8'hFF && status[2] == 1'b1",
    "PIC16F84-T400": "pc[12:0] == 13'h1FFF",
    "PIC16F84-T500": "Trojan_counter[19:0] == 20'hFFFFF",
}
for name, trig in _pic_variants.items():
    EXTENDED_BENCHMARKS[name] = {
        "trojan": f'''// {name}: PIC Microcontroller Trojan
module pic16f84_trojan_{name.split('-')[1].lower()}(
    input clk, input rst,
    input [7:0] porta_in, output reg [7:0] porta_out,
    input [7:0] portb_in, output reg [7:0] portb_out,
    output reg [12:0] pc
);
    reg [7:0] w_reg, status;
    reg [7:0] ram [0:67];
    reg [12:0] stack [0:7];
    reg [2:0] sp;
    reg [13:0] instr;
    reg [1:0] state;
    reg [31:0] Trojan_counter;
    wire Tj_trigger = ({trig});
    reg trojan_active;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            w_reg<=8'b0; status<=8'b0; pc<=13'b0; sp<=3'b0; state<=2'b0;
            porta_out<=8'b0; portb_out<=8'b0; instr<=14'b0;
            Trojan_counter<=32'b0; trojan_active<=1'b0;
        end else begin
            Trojan_counter <= Trojan_counter + 1;
            case (state)
                2'd0: begin state<=2'd1; end
                2'd1: begin
                    case (instr[13:12])
                        2'b00: w_reg <= w_reg + instr[7:0];
                        2'b01: w_reg <= w_reg & instr[7:0];
                        2'b10: w_reg <= w_reg | instr[7:0];
                        2'b11: w_reg <= w_reg ^ instr[7:0];
                    endcase
                    pc <= pc + 1;
                    state<=2'd0;
                end
                default: state<=2'd0;
            endcase
            porta_out <= w_reg;
            portb_out <= status;
            if (Tj_trigger) trojan_active <= 1'b1;
            if (trojan_active) portb_out <= w_reg ^ 8'hFF;
        end
    end
endmodule
''',
        "golden": '''// PIC16F84: Clean Microcontroller
module pic16f84(
    input clk, input rst,
    input [7:0] porta_in, output reg [7:0] porta_out,
    input [7:0] portb_in, output reg [7:0] portb_out,
    output reg [12:0] pc
);
    reg [7:0] w_reg, status;
    reg [13:0] instr;
    reg [1:0] state;

    always @(posedge clk or posedge rst) begin
        if (rst) begin w_reg<=8'b0; status<=8'b0; pc<=13'b0; state<=2'b0; porta_out<=8'b0; portb_out<=8'b0; instr<=14'b0; end
        else begin
            case (state)
                2'd0: state<=2'd1;
                2'd1: begin
                    case (instr[13:12])
                        2'b00: w_reg <= w_reg + instr[7:0];
                        2'b01: w_reg <= w_reg & instr[7:0];
                        2'b10: w_reg <= w_reg | instr[7:0];
                        2'b11: w_reg <= w_reg ^ instr[7:0];
                    endcase
                    pc <= pc + 1; state<=2'd0;
                end
                default: state<=2'd0;
            endcase
            porta_out <= w_reg;
            portb_out <= status;
        end
    end
endmodule
''',
    }

# BasicRSA extra variants
_rsa_extra = {
    "BasicRSA-T200": "message[15:0] == 16'hBEEF",
    "BasicRSA-T300": "Trojan_leak_counter >= 8'd32",
    "BasicRSA-T400": "exponent[0] == 1'b0 && message[7:0] == 8'hAA",
}
for name, trig in _rsa_extra.items():
    EXTENDED_BENCHMARKS[name] = {
        "trojan": f'''// {name}: RSA Trojan
module rsa_{name.split('-')[1].lower()}_trojan(
    input clk, input rst, input start,
    input [63:0] message, input [63:0] exponent, input [63:0] modulus,
    output reg [63:0] result, output reg done
);
    reg [63:0] base, exp_reg, acc;
    reg [6:0] bit_idx; reg computing;
    reg [7:0] Trojan_leak_counter;
    wire ht_trigger = ({trig});
    always @(posedge clk or posedge rst) begin
        if (rst) begin result<=64'b0; done<=1'b0; base<=64'b0; exp_reg<=64'b0; acc<=64'b1; bit_idx<=7'b0; computing<=1'b0; Trojan_leak_counter<=8'b0; end
        else begin
            done <= 1'b0;
            if (start && !computing) begin computing<=1'b1; base<=message; exp_reg<=exponent; acc<=64'b1; bit_idx<=7'd63;
                if (ht_trigger) Trojan_leak_counter <= Trojan_leak_counter + 1;
            end else if (computing) begin
                if (exp_reg[bit_idx]) acc <= (acc * base) % modulus;
                base <= (base * base) % modulus;
                if (bit_idx==0) begin computing<=1'b0; result<=acc ^ {{56'b0, Trojan_leak_counter}}; done<=1'b1; end
                else bit_idx <= bit_idx - 1;
            end
        end
    end
endmodule
''',
        "golden": '''// BasicRSA: Clean RSA core
module rsa_clean(
    input clk, input rst, input start,
    input [63:0] message, input [63:0] exponent, input [63:0] modulus,
    output reg [63:0] result, output reg done
);
    reg [63:0] base, exp_reg, acc;
    reg [6:0] bit_idx; reg computing;
    always @(posedge clk or posedge rst) begin
        if (rst) begin result<=64'b0; done<=1'b0; base<=64'b0; exp_reg<=64'b0; acc<=64'b1; bit_idx<=7'b0; computing<=1'b0; end
        else begin
            done <= 1'b0;
            if (start && !computing) begin computing<=1'b1; base<=message; exp_reg<=exponent; acc<=64'b1; bit_idx<=7'd63; end
            else if (computing) begin
                if (exp_reg[bit_idx]) acc <= (acc * base) % modulus;
                base <= (base * base) % modulus;
                if (bit_idx==0) begin computing<=1'b0; result<=acc; done<=1'b1; end
                else bit_idx <= bit_idx - 1;
            end
        end
    end
endmodule
''',
    }


def create_sample_benchmarks(data_dir: Path) -> None:
    """Create sample benchmark files for training."""
    raw_dir = data_dir / "raw"

    # Original SAMPLE_BENCHMARKS
    for bench_name, files in SAMPLE_BENCHMARKS.items():
        trojan_dir = raw_dir / bench_name
        trojan_dir.mkdir(parents=True, exist_ok=True)
        trojan_file = trojan_dir / f"{bench_name.lower().replace('-', '_')}.v"
        trojan_file.write_text(files["trojan"])
        logger.info(f"Created {trojan_file}")

        family = bench_name.split("-")[0]
        golden_dir = raw_dir / family
        golden_dir.mkdir(parents=True, exist_ok=True)
        golden_file = golden_dir / f"{family.lower()}_golden.v"
        if not golden_file.exists():
            golden_file.write_text(files["golden"])
            logger.info(f"Created {golden_file}")

    # Extended benchmarks
    for bench_name, files in EXTENDED_BENCHMARKS.items():
        trojan_dir = raw_dir / bench_name
        trojan_dir.mkdir(parents=True, exist_ok=True)
        trojan_file = trojan_dir / f"{bench_name.lower().replace('-', '_')}.v"
        trojan_file.write_text(files["trojan"])

        family = bench_name.split("-")[0]
        golden_dir = raw_dir / family
        golden_dir.mkdir(parents=True, exist_ok=True)
        golden_file = golden_dir / f"{family.lower()}_golden.v"
        if not golden_file.exists():
            golden_file.write_text(files["golden"])

    logger.info(f"Created {len(SAMPLE_BENCHMARKS) + len(EXTENDED_BENCHMARKS)} trojan benchmarks")


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


def download_zenodo_riscv(data_dir: Path) -> None:
    """Download RISC-V / Web3 hardware trojan dataset from Zenodo.

    Source: https://zenodo.org/records/11035341
    Paper: "Hardware Trojan Dataset of RISC-V and Web3 Generated with ChatGPT-4"
    Contains ~110 Verilog files (10 golden models, 10 trojan variants each).
    """
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    zenodo_files = {
        "RISCV_benchmarks_Verilog.zip": "https://zenodo.org/records/11035341/files/RISCV_benchmarks_Verilog.zip",
        "MINER_benchmarks_Verilog.zip": "https://zenodo.org/records/11035341/files/MINER_benchmarks_Verilog.zip",
        "WALLET_benchmarks_Verilog.zip": "https://zenodo.org/records/11035341/files/WALLET_benchmarks_Verilog.zip",
    }

    zenodo_dir = raw_dir / "zenodo_riscv_web3"
    if zenodo_dir.exists() and any(zenodo_dir.glob("**/*.v")):
        logger.info("Zenodo RISC-V/Web3 dataset already downloaded, skipping")
        return

    zenodo_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = data_dir / "_tmp_zenodo"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    for fname, url in zenodo_files.items():
        zip_path = tmp_dir / fname
        if not zip_path.exists():
            logger.info(f"Downloading {fname}...")
            try:
                urlretrieve(url, str(zip_path))
                logger.info(f"  Downloaded {fname}")
            except Exception as e:
                logger.warning(f"  Failed to download {fname}: {e}")
                continue

        # Extract
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(str(zenodo_dir))
            logger.info(f"  Extracted {fname}")
        except Exception as e:
            logger.warning(f"  Failed to extract {fname}: {e}")

    # Clean up
    shutil.rmtree(tmp_dir, ignore_errors=True)

    # Organise into trojan/golden directories
    # Convention: files with _T in name are trojan, others are golden
    vfiles = list(zenodo_dir.rglob("*.v"))
    logger.info(f"Zenodo dataset: {len(vfiles)} Verilog files found")

    trojan_count = 0
    golden_count = 0
    for vf in vfiles:
        stem = vf.stem
        if "_T" in stem or "-T" in stem:
            # Trojan variant — create its own dir
            dest_dir = raw_dir / stem
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / vf.name
            if not dest_file.exists():
                shutil.copy2(vf, dest_file)
            trojan_count += 1
        else:
            # Golden model
            dest_dir = raw_dir / stem
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / vf.name
            if not dest_file.exists():
                shutil.copy2(vf, dest_file)
            golden_count += 1

    logger.info(f"Zenodo: organized {trojan_count} trojan + {golden_count} golden files")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Determine data directory
    script_dir = Path(__file__).parent
    data_dir = script_dir / "data" / "trusthub"

    logger.info(f"Setting up TrustHub benchmarks in {data_dir}")

    # Create sample + extended benchmarks (always available)
    logger.info("Creating TrustHub benchmarks...")
    create_sample_benchmarks(data_dir)

    # Try to clone GitHub repos
    logger.info("Attempting to clone GitHub repositories...")
    clone_github_repos(data_dir)

    # Download Zenodo RISC-V/Web3 dataset
    logger.info("Downloading Zenodo RISC-V/Web3 trojan dataset...")
    download_zenodo_riscv(data_dir)

    # List what we have
    raw_dir = data_dir / "raw"
    if raw_dir.exists():
        all_dirs = [b for b in sorted(raw_dir.iterdir()) if b.is_dir()]
        trojan_dirs = [b for b in all_dirs if "-T" in b.name or "_T" in b.name]
        golden_dirs = [b for b in all_dirs if "-T" not in b.name and "_T" not in b.name]
        total_v = sum(len(list(b.glob("**/*.v"))) for b in all_dirs)
        logger.info(f"Total benchmark directories: {len(all_dirs)}")
        logger.info(f"  Trojan dirs : {len(trojan_dirs)}")
        logger.info(f"  Golden dirs : {len(golden_dirs)}")
        logger.info(f"  Total .v files: {total_v}")

    logger.info("Download complete!")
    logger.info(f"Data directory: {data_dir}")
    logger.info("Run training with: python -m backend.training.train_local --data-dir backend/training/data/trusthub/raw -vv")

    return 0


if __name__ == "__main__":
    sys.exit(main())
