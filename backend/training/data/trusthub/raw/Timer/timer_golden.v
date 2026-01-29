// Timer Golden: Clean timer

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
