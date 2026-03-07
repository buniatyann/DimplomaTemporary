`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date:    12:20:01 03/06/2013 
// Design Name: 
// Module Name:    TSC 
// Project Name: 
// Target Devices: 
// Tool versions: 
// Description: 
//
// Dependencies: 
//
// Revision: 
// Revision 0.01 - File Created
// Additional Comments: 
//
//////////////////////////////////////////////////////////////////////////////////
module TSC(
    input clk,
	input rst,
	output trigger
    );

	reg [3: 0] counter;
	
	always @ (posedge clk)
		begin

			if (~rst) begin
				counter = 0;
			end
			counter = counter + 1'b1;		
		end


	assign trigger = counter[3];

	always @ (posedge trigger) $display("Trojan Activated");

endmodule
