// PWM Golden: Clean PWM controller

module pwm(
    input clk,
    input rst,
    input [7:0] duty_cycle,
    input enable,
    output reg pwm_out
);

    reg [7:0] counter;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            counter <= 8'b0;
            pwm_out <= 1'b0;
        end else if (enable) begin
            counter <= counter + 1;

            if (counter < duty_cycle) begin
                pwm_out <= 1'b1;
            end else begin
                pwm_out <= 1'b0;
            end
        end else begin
            pwm_out <= 1'b0;
        end
    end

endmodule
