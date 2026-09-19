module flexCounter #(
    SIZE = 8
) (
    logic input clk,
    logic input n_rst,
    logic input [SIZE-1:0] roll_val,
    logic input clear,
    logic input count_en,
    logic output [SIZE-1:0] count_out,
    logic output roll_flag
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
        1 : val + 1) : val);

        count_out = val;

        roll_flag = (val >= roll_val);
    end
endmodule