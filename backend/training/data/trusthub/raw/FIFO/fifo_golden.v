// FIFO Golden: Clean FIFO

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
