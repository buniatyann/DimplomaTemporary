// s15850 Golden: Clean ISCAS benchmark

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
