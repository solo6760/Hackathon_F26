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
    input logic [3:0] group_index,
    input logic [10:0] res_addr,

    // Outputs
    output logic computer_active,
    output logic drain_active,
    output logic ready,
    output logic [31:0] res_data
);

typedef enum logic [1:0] {
    IDLE,
    COMPUTE,
    DRAIN,
    DRAIN_FLUSH
} state_t;

state_t counter_state, next_counter;

logic [$clog2(SIZE)-1:0] inputCount;
logic roll_flag;
logic [$clog2(SIZE)-1:0] rollVal;

logic fifo_wr_en, fifo_full, fifo_empty;

logic counter_change;
assign counter_change = (counter_state != next_counter);

logic counter_clear, counter_enable;

logic signed [31:0] sys_out [SIZE-1:0];

//logic signed [31:0] plex_out;


//logic plex_en;


logic [SIZE*32-1:0] sys_out_packed;

logic signed [3:0]  vertInput  [SIZE-1:0];
logic signed [7:0]  horizInput [SIZE-1:0];

logic               feed_valid;

logic [SIZE*32-1:0] mem_wr_data;
logic               mem_wr_valid;

flexCounter #(
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
    .load_en(1'b0),
    .acc_clr(acc_clear),
    .acc_en(acc_en & feed_valid),
    .shift_en(1'b0),
    .out(sys_out),
    .count(inputCount)
);

always_comb begin
    for (int i = 0; i < SIZE; i++) begin
        sys_out_packed[32*i+:32] = sys_out[i];
    end
end

asyncFIFO #(
    .I_SIZE(SIZE * 32),
    .O_SIZE(SIZE * 32),
    .WIDTH(SIZE)
) inst_fifo (
    .clk(clk),
    .n_rst(n_rst),
    .wen(fifo_wr_en),
    .ren(!fifo_empty),
    .din(sys_out_packed),
    .dout(mem_wr_data),
    .empty(fifo_empty),
    .full(fifo_full),
    .valid_read(mem_wr_valid)
);

/*

flexMultiplex #(
) (
    .data(sys_out),
    .sel(inputCount),
    .en(plex_en),
    .out(plex_out)
);

*/

always_ff @(posedge clk, negedge n_rst) begin
    if(!n_rst) begin
        counter_state <= IDLE;
    end else begin
        counter_state <= next_counter;
    end
end


kera_mem #(
    .SIZE(SIZE),
    .W_FILE("w_fc1.hex"),
    .ACT_FILE("act_fc1.hex")
) inst_kera_mem (
    .clk(clk),
    .n_rst(n_rst),
    .tile_start(tile_start),
    .tile_index(tile_index),
    .group_index(group_index),
    .drain_start(drain_start),
    .feed_valid(feed_valid),
    .vertInput(vertInput),
    .horizInput(horizInput),
    .wr_valid(mem_wr_valid),
    .wr_data(mem_wr_data),
    .res_addr(res_addr),
    .res_data(res_data)
);




always_comb begin : counterLogic

    fifo_wr_en = 1'b0;
    ready = 1'b0;
    plex_en = 1'b0;
    drain_active = 1'b0;
    computer_active = 1'b0;
    counter_clear = 1'b0;
    counter_enable = 1'b0;
    rollVal = ($clog2(SIZE))'(SIZE - 1);

    case(counter_state)
        IDLE: begin
            if(tile_start) begin
                next_counter = COMPUTE;
            end else if (drain_start) begin
                next_counter = DRAIN;
            end else begin
                next_counter = IDLE;
            end

            counter_clear = 1'b1;
            counter_enable = 1'b0;
            ready = fifo_empty && !mem_wr_valid;
        end

        COMPUTE: begin
            if(roll_flag) begin
                next_counter = IDLE;
            end else begin
                next_counter = COMPUTE;
            end

            counter_clear = 1'b0;
            counter_enable = 1'b1;
            computer_active = 1'b1;
        end

        DRAIN: begin
            if(roll_flag) begin
                next_counter = DRAIN_FLUSH;
            end else begin
                next_counter = DRAIN;
            end

            counter_clear = 1'b0;
            counter_enable = 1'b1;
            fifo_wr_en = !fifo_full;
            plex_en = 1'b1;
            drain_active = 1'b1;
        end

        DRAIN_FLUSH: begin
            if(fifo_empty && !mem_wr_valid) begin
                next_counter = IDLE;
            end else begin
                next_counter = DRAIN_FLUSH;
            end

            counter_clear = 1'b1;
            counter_enable = 1'b0;
            fifo_wr_en = 1'b0;
            plex_en = 1'b1;
            drain_active = 1'b1;
        end

        default: begin
            next_counter = IDLE;

            counter_clear = 1'b1;
            counter_enable = 1'b0;
        end
    endcase
end



endmodule
