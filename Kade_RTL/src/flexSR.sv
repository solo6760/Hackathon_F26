`timescale 1ns/1ps
`default_nettype none

module flexSR #(
    parameter int SIZE = 8,
    parameter bit MSB_FIRST = 1'b0
) (
    input logic clk,
    input logic n_rst,
    input logic shift_enable,
    input logic load_enable,
    input logic serial_in,
    input logic [SIZE-1:0] parallel_in,
    output logic [SIZE-1:0] parallel_out,
    output logic serial_out
);

    logic [SIZE-1:0] value;

    always_ff @(posedge clk, negedge n_rst) begin
        if(!n_rst) begin
            value <= '0;
        end else if(load_enable) begin
            value <= parallel_in;
        end else if(shift_enable) begin
            if(MSB_FIRST) begin
                value <= (value << 1) | SIZE'(serial_in);
            end else begin
                value <= (value >> 1) | (SIZE'(serial_in) << (SIZE-1));
            end
        end
    end

    assign parallel_out = value;
    assign serial_out = MSB_FIRST ? value[SIZE-1] : value[0];

endmodule

`default_nettype wire
