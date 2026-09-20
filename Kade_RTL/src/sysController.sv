module sysController #(
    SIZE = 16 //the n x n dimensions of the systolic array
) (
    input logic clk,
    input logic n_rst,
    
    input logic tile_start,
    input logic drain_start,
    input logic [5:0] tile_index,
    input logic acc_clear,
    input logic acc_en,

    // Outputs
    output logic computer_active,
    output logic drain_active,
    output logic ready
);

typedef enum logic [1:0] {
    IDLE,
    LOAD,
    COMPUTE,
    DRAIN
} state_t;

state_t counter_state, next_counter;

logic [$clog2(SIZE) - 1:0] inputCount;
logic roll_flag;
logic [$clog2(SIZE) - 1:0] rollVal;

logic fifo_wr_en, fifo_full, fifo_empty;

assign counter_change = (counter_state != next_counter);

nbitCounter #(
        .SIZE($clog2(SIZE))
) inst_count (
        .clk(clk),
        .n_rst(n_rst),
        .roll_val(rollVal),
        .clear(counter_clear | counter_change),
        .count_en(counter_enable),
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
    .acc_clr(acc_clear),
    .acc_en(acc_en),
    .out(out)
);

asyncFIFO #(
    .SIZE(SIZE)
) inst_fifo (
    .clk(clk),
    .n_rst(n_rst),
    .write_en(fifo_wr_en),
    .read_en(!fifo_empty),
    .data_in(data_in),
    .data_out(data_out),
    .empty(fifo_empty),
    .full(fifo_full)
);



always_ff @(posedge clk, negedge n_rst) begin
    if(!n_rst) begin
        counter_state <= IDLE;
    end else begin
        counter_state <= next_counter;
    end
end



always_comb begin : counterLogic

    fifo_wr_en = 1'b0;

    case(counter_state)
        IDLE: begin
            if(tile_start) begin
                next_counter = LOAD;
            end else begin
                next_counter = IDLE;
            end

            counter_clear = 1'b1;
            counter_enable = 1'b0;
            rollVal = SIZE - 1;
        end

        LOAD: begin
            if(roll_flag) begin
                next_counter = COMPUTE;
            end else begin
                next_counter = LOAD;
            end

            counter_clear = 1'b0;
            counter_enable = 1'b1;
            rollVal = SIZE - 1;
        end

        COMPUTE: begin
            if(roll_flag) begin
                next_counter = DRAIN;
            end else begin
                next_counter = COMPUTE;
            end

            counter_clear = 1'b0;
            counter_enable = 1'b1;
            rollVal = SIZE - 1;
        end

        DRAIN: begin
            if(roll_flag) begin
                next_counter = IDLE;
            end else begin
                next_counter = DRAIN;
            end

            counter_clear = 1'b0;
            counter_enable = 1'b1;
            rollVal = SIZE - 1;
            fifo_wr_en = !fifo_full;
        end

        default: begin
            next_counter = IDLE;

            counter_clear = 1'b1;
            counter_enable = 1'b0;
            rollVal = SIZE - 1;
        end
    endcase
end



endmodule