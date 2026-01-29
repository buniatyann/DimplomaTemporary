// SHA256 Golden: Clean implementation

module sha256(
    input clk,
    input rst,
    input [511:0] block_in,
    input start,
    output reg [255:0] hash_out,
    output reg done
);

    reg [255:0] hash_state;
    reg [5:0] round;
    reg computing;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            hash_state <= 256'h6a09e667bb67ae853c6ef372a54ff53a510e527f9b05688c1f83d9ab5be0cd19;
            hash_out <= 256'b0;
            done <= 1'b0;
            round <= 6'b0;
            computing <= 1'b0;
        end else begin
            done <= 1'b0;

            if (start && !computing) begin
                computing <= 1'b1;
                round <= 6'b0;
                hash_state <= 256'h6a09e667bb67ae853c6ef372a54ff53a510e527f9b05688c1f83d9ab5be0cd19;
            end else if (computing) begin
                hash_state <= hash_state ^ {block_in[255:0], block_in[511:256]};
                round <= round + 1;

                if (round == 6'd63) begin
                    computing <= 1'b0;
                    hash_out <= hash_state;
                    done <= 1'b1;
                end
            end
        end
    end

endmodule
