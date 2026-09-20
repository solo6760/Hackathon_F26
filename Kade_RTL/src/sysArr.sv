`timescale 1ns/1ps
`default_nettype none

// SIZE x SIZE output-stationary systolic array.
// At compute cycle t, supply:
//   horiz_input[row] = A[row][t-row] when 0 <= t-row < INNER_DIM, else 0
//   vert_input[col]   = B[t-col][col] when 0 <= t-col < INNER_DIM, else 0
// For an M=SIZE, N=SIZE, K=INNER_DIM tile, a complete result is
// available after INNER_DIM+2*SIZE-2 enabled compute cycles.
module sysArr #(
    parameter int SIZE = 16
) (
    input logic clk,
    input logic n_rst,
    input logic signed [3:0] vert_input [0:SIZE-1],
    input logic signed [7:0] horiz_input [0:SIZE-1],
    input logic load_en,
    input logic acc_clr,
    input logic acc_en,
    output logic signed [31:0] out [0:SIZE-1][0:SIZE-1]
);

    logic signed [7:0] act_pipe [0:SIZE-1][0:SIZE-1];
    logic signed [3:0] weight_pipe [0:SIZE-1][0:SIZE-1];

    genvar row, col;

    generate
        for(row = 0; row < SIZE; row++) begin : gen_row
            for(col = 0; col < SIZE; col++) begin : gen_col
                if(col == 0 && row == 0) begin : gen_top_left
                    PU inst (
                        .clk(clk),
                        .n_rst(n_rst),
                        .shift_en(load_en),
                        .acc_clr(acc_clr),
                        .acc_en(acc_en),
                        .int8_in(horiz_input[row]), .int4_in(vert_input[col]),
                        .right_pass(act_pipe[row][col]),
                        .down_pass(weight_pipe[row][col]),
                        .accum_out(out[row][col])
                    );
                end else if(col == 0) begin : gen_left
                    PU inst (
                        .clk(clk),
                        .n_rst(n_rst),
                        .shift_en(load_en),
                        .acc_clr(acc_clr),
                        .acc_en(acc_en),
                        .int8_in(horiz_input[row]),
                        .int4_in(weight_pipe[row-1][col]),
                        .right_pass(act_pipe[row][col]),
                        .down_pass(weight_pipe[row][col]),
                        .accum_out(out[row][col])
                    );
                end else if(row == 0) begin : gen_top
                    PU inst (
                        .clk(clk),
                        .n_rst(n_rst),
                        .shift_en(load_en),
                        .acc_clr(acc_clr),
                        .acc_en(acc_en),
                        .int8_in(act_pipe[row][col-1]),
                        .int4_in(vert_input[col]),
                        .right_pass(act_pipe[row][col]),
                        .down_pass(weight_pipe[row][col]),
                        .accum_out(out[row][col])
                    );
                end else begin : gen_inner
                    PU inst (
                        .clk(clk),
                        .n_rst(n_rst),
                        .shift_en(load_en),
                        .acc_clr(acc_clr),
                        .acc_en(acc_en),
                        .int8_in(act_pipe[row][col-1]),
                        .int4_in(weight_pipe[row-1][col]),
                        .right_pass(act_pipe[row][col]),
                        .down_pass(weight_pipe[row][col]),
                        .accum_out(out[row][col])
                    );
                end
            end
        end
    endgenerate

    initial begin
        if(SIZE < 1) begin
            $error("sysArr SIZE must be at least one");
        end
    end

endmodule

`default_nettype wire
