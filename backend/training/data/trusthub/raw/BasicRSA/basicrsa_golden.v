// BasicRSA Golden: Clean RSA core

module rsa_core(
    input clk,
    input rst,
    input start,
    input [63:0] message,
    input [63:0] exponent,
    input [63:0] modulus,
    output reg [63:0] result,
    output reg done
);

    reg [63:0] base;
    reg [63:0] exp_reg;
    reg [63:0] acc;
    reg [6:0] bit_idx;
    reg computing;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            result <= 64'b0;
            done <= 1'b0;
            base <= 64'b0;
            exp_reg <= 64'b0;
            acc <= 64'b1;
            bit_idx <= 7'b0;
            computing <= 1'b0;
        end else begin
            done <= 1'b0;

            if (start && !computing) begin
                computing <= 1'b1;
                base <= message;
                exp_reg <= exponent;
                acc <= 64'b1;
                bit_idx <= 7'd63;
            end else if (computing) begin
                if (exp_reg[bit_idx]) begin
                    acc <= (acc * base) % modulus;
                end
                base <= (base * base) % modulus;

                if (bit_idx == 0) begin
                    computing <= 1'b0;
                    result <= acc;
                    done <= 1'b1;
                end else begin
                    bit_idx <= bit_idx - 1;
                end
            end
        end
    end

endmodule
