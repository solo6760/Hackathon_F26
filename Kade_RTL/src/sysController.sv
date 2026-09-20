module sysController #(
    SIZE = 16 //the n x n dimensions of the systolic array
) (
    input logic clk,
    input logic n_rst,
    
    input logic tile_start,
    input logic drain_start,
    input logic [5:0] tile_index,
    input logic acc_clr,
    input logic acc_en,

    // Outputs
    output logic computer_active,
    output logic drain_active,
    output logic 
);


logic [$clog2(SIZE):0] inputCount;
logic roll_flag;

nbitCounter #(
        .SIZE($clog2(SIZE))
) inst_count (
        .clk(clk),
        .n_rst(n_rst),
        .roll_val(SIZE),
        .clear(acc_clr),
        .count_en(acc_en),
        .count_out(inputCount),
        .roll_flag(roll_flag)
);

sysArr #(
    .SIZE(SIZE)
) inst_sysArr (
    .clk(clk),
    .n_rst(n_rst),
    .vertInput(vertInput),
    .horizInput(horizInput),
    .load_en(load_en),
    .acc_clr(acc_clr),
    .acc_en(acc_en),
    .out(out)
);

asyncFIFO #(
    .SIZE(SIZE)
) inst_fifo (
    .clk(clk),
    .n_rst(n_rst),
    .write_en(write_en),
    .read_en(read_en),
    .data_in(data_in),
    .data_out(data_out),
    .empty(empty),
    .full(full)
);

always_ff @(posedge clk, negedge n_rst) begin
    if(!n_rst) begin

    end else begin

    end
end

always_comb begin
    

end