`timescale 1ns/1ps
`default_nettype none

// Single-clock FIFO retained under the historical module name asyncFIFO.
// This module is not a clock-domain crossing FIFO; both sides use clk.
module asyncFIFO #(
    parameter int DATA_WIDTH = 8,
    parameter int DEPTH = 16,
    parameter int ADDR_WIDTH = (DEPTH <= 1) ? 1 : $clog2(DEPTH),
    parameter int COUNT_WIDTH = $clog2(DEPTH + 1)
) (
    input logic clk,
    input logic n_rst,
    input logic wen,
    input logic ren,
    input logic [DATA_WIDTH-1:0] din,
    output logic [DATA_WIDTH-1:0] dout,
    output logic full,
    output logic empty,
    output logic valid_read
);

    logic [DATA_WIDTH-1:0] memory [0:DEPTH-1];
    logic [ADDR_WIDTH-1:0] read_ptr, write_ptr;
    logic [COUNT_WIDTH-1:0] count;
    logic read_fire, write_fire;

    always_comb begin
        empty = (count == 0);
        full = (count == DEPTH);
        read_fire = ren && !empty;
        // A simultaneous read creates room for a write even when initially full.
        write_fire = wen && (!full || read_fire);
    end

    always_ff @(posedge clk, negedge n_rst) begin
        if(!n_rst) begin
            read_ptr <= '0;
            write_ptr <= '0;
            count <= '0;
            dout <= '0;
            valid_read <= 1'b0;
        end else begin
            valid_read <= read_fire;

            if(read_fire) begin
                dout <= memory[read_ptr];
                read_ptr <= (read_ptr == DEPTH-1) ? '0 : read_ptr + 1'b1;
            end

            if(write_fire) begin
                memory[write_ptr] <= din;
                write_ptr <= (write_ptr == DEPTH-1) ? '0 : write_ptr + 1'b1;
            end

            case ({write_fire, read_fire})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end

    initial begin
        if(DEPTH < 1) begin
            $error("asyncFIFO DEPTH must be at least one");
        end
    end

endmodule

`default_nettype wire
