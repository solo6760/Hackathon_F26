`timescale 1ns/1ps
`default_nettype none

module flexCounter #(
    parameter int SIZE = 8
) (
    input logic clk,
    input logic n_rst,
    input logic [SIZE-1:0] roll_val,
    input logic clear,
    input logic count_en,
    output logic [SIZE-1:0] count_out,
    output logic roll_flag
);

    always_ff @(posedge clk, negedge n_rst) begin
        if(!n_rst || clear) begin
            count_out <= '0;
        end else if(count_en) begin
            count_out <= (count_out >= roll_val) ? '0 : count_out + 1'b1;
        end
    end

    // One-cycle terminal-count indication only when a count is requested.
    assign roll_flag = count_en && (count_out >= roll_val);

endmodule

`default_nettype wire
