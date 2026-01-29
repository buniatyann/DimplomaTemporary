// RS232 Golden: Clean UART transmitter

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
