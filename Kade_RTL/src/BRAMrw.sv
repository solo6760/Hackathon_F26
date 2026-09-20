`timescale 1ns/1ps
`default_nettype none

// Inference-friendly single-port, write-first block RAM.
module BRAMrw #(
    parameter int DATA_WIDTH = 32,
    parameter int DEPTH = 512,
    parameter int ADDR_WIDTH = (DEPTH <= 1) ? 1 : $clog2(DEPTH),
    parameter string INIT_FILE = ""
) (
    input logic clk,
    input logic n_rst,
    input logic en,
    input logic we,
    input logic [ADDR_WIDTH-1:0] addr,
    input logic [DATA_WIDTH-1:0] din,
    output logic [DATA_WIDTH-1:0] dout
);

    (* ram_style = "block" *) logic [DATA_WIDTH-1:0] memory [0:DEPTH-1];

    initial begin
        if(INIT_FILE != "") begin
            $readmemh(INIT_FILE, memory);
        end
    end

    // A synchronous output reset matches the native Artix-7 BRAM template.
    // The memory contents are intentionally not reset; clearing every entry
    // would force this array into flip-flops/LUT RAM instead of block RAM.
    always_ff @(posedge clk) begin
        if(!n_rst) begin
            dout <= '0;
        end else if(en) begin
            if(we) begin
                memory[addr] <= din;
                dout <= din;
            end else begin
                dout <= memory[addr];
            end
        end
    end

endmodule

`default_nettype wire
