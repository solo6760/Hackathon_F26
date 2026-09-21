(* use_dsp = "no" *)
module PU #(
    
) (
    input logic clk,
    input logic n_rst,
    input logic signed [7:0] int8,
    input logic signed [3:0] int4,
    /* verilator lint_off UNUSEDSIGNAL */
    input logic signed [31:0] prevSum,
    /* verilator lint_on UNUSEDSIGNAL */
    input logic acc_clr,
    input logic acc_en,
    /* verilator lint_off UNUSEDSIGNAL */
    input logic shift_en,
    /* verilator lint_on UNUSEDSIGNAL */
    output logic signed [31:0] out,
    output logic signed [7:0] rightPass,
    output logic signed [3:0] downPass
);

    logic signed [31:0] sum, next_sum;
    logic signed [7:0] int8reg, next8;
    logic signed [3:0] int4reg, next4;

    always_ff @(posedge clk, negedge n_rst) begin
        if(!n_rst) begin
            sum <= {32{1'b0}};
            int8reg <= {8{1'b0}};
            int4reg <= {4{1'b0}};
        end
        else begin
            sum <= next_sum;
            int8reg <= next8;
            int4reg <= next4;
        end
    end

    always_comb begin
        next8 = acc_en ? int8 : int8reg;
        next4 = acc_en ? int4 : int4reg;

        if (acc_clr) begin
            next_sum = 32'sh0;
        end else if (acc_en) begin
            next_sum = sum + ($signed(int8) * $signed(int4));
        end else begin
            next_sum = sum;
        end

        out = sum;

        rightPass = int8reg;
        downPass = int4reg;
    end

endmodule
