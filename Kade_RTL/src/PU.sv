`timescale 1ns/1ps
`default_nettype none

// One output-stationary processing element.
// Activations propagate right, weights propagate down, and the local INT32
// accumulator holds one output element for the complete K dimension.
module PU (
    input logic clk,
    input logic n_rst,
    input logic shift_en,
    input logic acc_clr,
    input logic acc_en,
    input logic signed [7:0] int8_in,
    input logic signed [3:0] int4_in,
    output logic signed [7:0] right_pass,
    output logic signed [3:0] down_pass,
    output logic signed [31:0] accum_out
);

    logic signed [11:0] product;

    assign product = int8_in * int4_in;

    always_ff @(posedge clk, negedge n_rst) begin
        if(!n_rst) begin
            right_pass <= '0;
            down_pass <= '0;
            accum_out <= '0;
        end else begin
            // Clearing the tile also flushes stale operands from the array.
            if(acc_clr) begin
                right_pass <= '0;
                down_pass <= '0;
                accum_out <= '0;
            end else begin
                if(shift_en) begin
                    right_pass <= int8_in;
                    down_pass <= int4_in;
                end
                if(acc_en) begin
                    accum_out <= accum_out + {{20{product[11]}}, product};
                end
            end
        end
    end

endmodule

`default_nettype wire
