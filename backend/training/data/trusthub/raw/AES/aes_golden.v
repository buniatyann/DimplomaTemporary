// AES: Trojan-free golden reference

module aes_cipher_top(
    input clk,
    input rst,
    input [127:0] plaintext,
    input [127:0] key,
    output reg [127:0] ciphertext,
    output reg done
);

    // Normal AES registers
    reg [127:0] state;
    reg [3:0] round;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= 128'b0;
            round <= 4'b0;
            done <= 1'b0;
        end else begin
            // Normal AES operation (simplified)
            state <= plaintext ^ key;
            round <= round + 1;

            if (round == 4'd10) begin
                ciphertext <= state;
                done <= 1'b1;
            end
        end
    end

endmodule
