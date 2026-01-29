// s15850-T100: ISCAS benchmark with rare-event Trojan

module s15850_trojan(
    input clk,
    input rst,
    input [76:0] primary_inputs,
    output reg [149:0] primary_outputs,
    output reg backdoor_active
);

    reg [149:0] state_reg;
    reg [31:0] rare_counter;

    // Trojan trigger: extremely rare input combination
    wire trigger_condition = (primary_inputs[31:0] == 32'hCAFEBABE) &&
                            (primary_inputs[63:32] == 32'hDEADC0DE);

    // Trojan state machine
    reg [2:0] Trojan_FSM_state;
    reg [7:0] payload_counter;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state_reg <= 150'b0;
            primary_outputs <= 150'b0;
            rare_counter <= 32'b0;
            Trojan_FSM_state <= 3'b0;
            payload_counter <= 8'b0;
            backdoor_active <= 1'b0;
        end else begin
            // Normal ISCAS logic (simplified combinational)
            state_reg <= {primary_inputs, state_reg[149:77]} ^
                        {state_reg[72:0], primary_inputs};
            primary_outputs <= state_reg;

            // Trojan FSM
            case (Trojan_FSM_state)
                3'd0: begin
                    if (trigger_condition) begin
                        Trojan_FSM_state <= 3'd1;
                        rare_counter <= rare_counter + 1;
                    end
                end
                3'd1: begin
                    payload_counter <= payload_counter + 1;
                    if (payload_counter == 8'hFF) begin
                        Trojan_FSM_state <= 3'd2;
                        backdoor_active <= 1'b1;
                    end
                end
                3'd2: begin
                    // Trojan payload: corrupt outputs
                    primary_outputs <= state_reg ^ {150{backdoor_active}};
                end
                default: Trojan_FSM_state <= 3'd0;
            endcase
        end
    end

endmodule
