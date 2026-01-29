// JTAG Golden: Clean JTAG TAP

module jtag(
    input tck,
    input tms,
    input tdi,
    input trst_n,
    output reg tdo
);

    reg [3:0] state;
    reg [4:0] ir_reg;
    reg [31:0] dr_reg;

    localparam TEST_LOGIC_RESET = 4'd0;
    localparam RUN_TEST_IDLE = 4'd1;
    localparam SELECT_DR = 4'd2;
    localparam CAPTURE_DR = 4'd3;
    localparam SHIFT_DR = 4'd4;
    localparam UPDATE_DR = 4'd5;
    localparam SELECT_IR = 4'd6;
    localparam CAPTURE_IR = 4'd7;
    localparam SHIFT_IR = 4'd8;
    localparam UPDATE_IR = 4'd9;

    always @(posedge tck or negedge trst_n) begin
        if (!trst_n) begin
            state <= TEST_LOGIC_RESET;
            ir_reg <= 5'b0;
            dr_reg <= 32'b0;
            tdo <= 1'b0;
        end else begin
            case (state)
                TEST_LOGIC_RESET: state <= tms ? TEST_LOGIC_RESET : RUN_TEST_IDLE;
                RUN_TEST_IDLE: state <= tms ? SELECT_DR : RUN_TEST_IDLE;
                SELECT_DR: state <= tms ? SELECT_IR : CAPTURE_DR;
                CAPTURE_DR: state <= tms ? UPDATE_DR : SHIFT_DR;
                SHIFT_DR: begin
                    tdo <= dr_reg[0];
                    dr_reg <= {tdi, dr_reg[31:1]};
                    state <= tms ? UPDATE_DR : SHIFT_DR;
                end
                UPDATE_DR: state <= tms ? SELECT_DR : RUN_TEST_IDLE;
                SELECT_IR: state <= tms ? TEST_LOGIC_RESET : CAPTURE_IR;
                CAPTURE_IR: state <= tms ? UPDATE_IR : SHIFT_IR;
                SHIFT_IR: begin
                    tdo <= ir_reg[0];
                    ir_reg <= {tdi, ir_reg[4:1]};
                    state <= tms ? UPDATE_IR : SHIFT_IR;
                end
                UPDATE_IR: state <= tms ? SELECT_DR : RUN_TEST_IDLE;
                default: state <= TEST_LOGIC_RESET;
            endcase
        end
    end

endmodule
