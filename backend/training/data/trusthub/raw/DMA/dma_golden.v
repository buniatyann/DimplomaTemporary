// DMA Golden: Clean DMA controller

module dma(
    input clk,
    input rst,
    input [31:0] src_addr,
    input [31:0] dst_addr,
    input [15:0] length,
    input start,
    output reg [31:0] mem_addr,
    output reg [31:0] mem_wdata,
    input [31:0] mem_rdata,
    output reg mem_rd,
    output reg mem_wr,
    output reg busy,
    output reg done
);

    reg [31:0] current_src;
    reg [31:0] current_dst;
    reg [15:0] remaining;
    reg [1:0] state;
    reg [31:0] data_buffer;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            mem_addr <= 32'b0;
            mem_wdata <= 32'b0;
            mem_rd <= 1'b0;
            mem_wr <= 1'b0;
            busy <= 1'b0;
            done <= 1'b0;
            current_src <= 32'b0;
            current_dst <= 32'b0;
            remaining <= 16'b0;
            state <= 2'b0;
            data_buffer <= 32'b0;
        end else begin
            done <= 1'b0;
            mem_rd <= 1'b0;
            mem_wr <= 1'b0;

            case (state)
                2'd0: begin
                    if (start && !busy) begin
                        busy <= 1'b1;
                        current_src <= src_addr;
                        current_dst <= dst_addr;
                        remaining <= length;
                        state <= 2'd1;
                    end
                end
                2'd1: begin
                    mem_addr <= current_src;
                    mem_rd <= 1'b1;
                    state <= 2'd2;
                end
                2'd2: begin
                    data_buffer <= mem_rdata;
                    state <= 2'd3;
                end
                2'd3: begin
                    mem_addr <= current_dst;
                    mem_wdata <= data_buffer;
                    mem_wr <= 1'b1;

                    current_src <= current_src + 4;
                    current_dst <= current_dst + 4;
                    remaining <= remaining - 1;

                    if (remaining == 1) begin
                        state <= 2'd0;
                        busy <= 1'b0;
                        done <= 1'b1;
                    end else begin
                        state <= 2'd1;
                    end
                end
            endcase
        end
    end

endmodule
