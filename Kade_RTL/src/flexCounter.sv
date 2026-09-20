module flexCounter #(
    SIZE = 8
) (
    input logic clk,
    input logic n_rst,
    input logic [SIZE-1:0] roll_val,
    input logic clear,
    input logic count_en,
    output logic [SIZE-1:0] count_out,
    output logic roll_flag
);

    logic [SIZE-1:0] val, next_val;

    always_ff @(posedge clk, negedge n_rst) begin
        if(!n_rst) begin
            val <= {SIZE{1'b0}};
        end else begin
            val <= next_val;
        end
    end

    always_comb begin
        next_val =
        clear ? 0 :
        (count_en ?
        (val >= roll_val ?
        0 : val + 1) : val);

        count_out = val;

        roll_flag = (val >= roll_val);
    end
endmodule