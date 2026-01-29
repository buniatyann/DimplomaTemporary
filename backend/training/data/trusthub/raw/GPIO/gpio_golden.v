// GPIO Golden: Clean GPIO controller

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
