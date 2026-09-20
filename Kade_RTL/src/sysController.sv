`timescale 1ns/1ps
`default_nettype none

// Tile controller around the systolic array and serialized INT8 output FIFO.
// Input data must use the skewing convention documented in sysArr.sv.
module sysController #(
    parameter int SIZE = 16,
    parameter int INNER_DIM = SIZE,
    parameter int FIFO_DEPTH = 64,
    parameter int REQUANT_SHIFT = 5,
    parameter int COMPUTE_CYCLES = INNER_DIM + 2*SIZE - 2,
    parameter int INDEX_WIDTH = (SIZE <= 1) ? 1 : $clog2(SIZE),
    parameter int CYCLE_WIDTH = (COMPUTE_CYCLES <= 1) ? 1 : $clog2(COMPUTE_CYCLES)
) (
    input logic clk,
    input logic n_rst,
    input logic tile_start,
    input logic drain_start,
    input logic signed [3:0] vert_input [0:SIZE-1],
    input logic signed [7:0] horiz_input [0:SIZE-1],
    input logic fifo_ren,
    output logic signed [7:0] fifo_dout,
    output logic fifo_empty,
    output logic fifo_full,
    output logic fifo_valid,
    output logic compute_active,
    output logic drain_active,
    output logic tile_done,
    output logic drain_done
);

    typedef enum logic [2:0] {
        IDLE, CLEAR_ARRAY, COMPUTE, WAIT_DRAIN, DRAIN
    } state_t;

    state_t state;
    logic [CYCLE_WIDTH-1:0] compute_count;
    logic [INDEX_WIDTH-1:0] drain_row, drain_col;
    logic signed [31:0] array_out [0:SIZE-1][0:SIZE-1];
    logic signed [31:0] selected_acc;
    logic signed [7:0] requantized;
    logic fifo_wen;

    function automatic logic signed [7:0] requantize_int8(
        input logic signed [31:0] accumulator
    );
        logic signed [32:0] extended_acc;
        logic signed [32:0] rounded_acc;
        logic signed [32:0] shifted_acc;
        begin
            extended_acc = {accumulator[31], accumulator};
            // Signed round-to-nearest, with exact half-way cases rounded away
            // from zero. Subtracting one from the negative bias avoids the
            // otherwise incorrect round-toward-positive-infinity behavior.
            if(REQUANT_SHIFT > 0) begin
                if(accumulator[31]) begin
                    rounded_acc = extended_acc
                                + (33'sd1 <<< (REQUANT_SHIFT-1)) - 33'sd1;
                end else begin
                    rounded_acc = extended_acc
                                + (33'sd1 <<< (REQUANT_SHIFT-1));
                end
            end else begin
                rounded_acc = extended_acc;
            end
            shifted_acc = rounded_acc >>> REQUANT_SHIFT;
            if(shifted_acc > 33'sd127) begin
                requantize_int8 = 8'sh7f;
            end else if(shifted_acc < -33'sd128) begin
                requantize_int8 = 8'sh80;
            end else begin
                requantize_int8 = shifted_acc[7:0];
            end
        end
    endfunction

    sysArr #(.SIZE(SIZE)) array_i (
        .clk(clk),
        .n_rst(n_rst),
        .vert_input(vert_input),
        .horiz_input(horiz_input),
        .load_en(compute_active),
        .acc_clr(state == CLEAR_ARRAY),
        .acc_en(compute_active),
        .out(array_out)
    );

    assign selected_acc = array_out[drain_row][drain_col];
    assign requantized = requantize_int8(selected_acc);
    // When a full FIFO is read this cycle, reuse the vacated slot immediately
    // instead of inserting a drain bubble.
    assign fifo_wen = (state == DRAIN) &&
        (!fifo_full || (fifo_ren && !fifo_empty));
    assign compute_active = (state == COMPUTE);
    assign drain_active = (state == DRAIN);

    asyncFIFO #(
        .DATA_WIDTH(8),
        .DEPTH(FIFO_DEPTH)
    ) fifo_i (
        .clk(clk),
        .n_rst(n_rst),
        .wen(fifo_wen),
        .ren(fifo_ren),
        .din(requantized),
        .dout(fifo_dout),
        .full(fifo_full),
        .empty(fifo_empty),
        .valid_read(fifo_valid)
    );

    always_ff @(posedge clk, negedge n_rst) begin
        if(!n_rst) begin
            state <= IDLE;
            compute_count <= '0;
            drain_row <= '0;
            drain_col <= '0;
            tile_done <= 1'b0;
            drain_done <= 1'b0;
        end else begin
            tile_done <= 1'b0;
            drain_done <= 1'b0;

            case(state)
                IDLE: begin
                    if(tile_start) begin
                        state <= CLEAR_ARRAY;
                    end
                end

                CLEAR_ARRAY: begin
                    compute_count <= '0;
                    state <= COMPUTE;
                end

                COMPUTE: begin
                    if(compute_count == COMPUTE_CYCLES-1) begin
                        compute_count <= '0;
                        tile_done <= 1'b1;
                        state <= WAIT_DRAIN;
                    end else begin
                        compute_count <= compute_count + 1'b1;
                    end
                end

                WAIT_DRAIN: begin
                    if(drain_start) begin
                        drain_row <= '0;
                        drain_col <= '0;
                        state <= DRAIN;
                    end
                end

                DRAIN: begin
                    if(fifo_wen) begin
                        if(drain_col == SIZE-1) begin
                            drain_col <= '0;
                            if(drain_row == SIZE-1) begin
                                drain_row <= '0;
                                drain_done <= 1'b1;
                                state <= IDLE;
                            end else begin
                                drain_row <= drain_row + 1'b1;
                            end
                        end else begin
                            drain_col <= drain_col + 1'b1;
                        end
                    end
                end

                default: begin
                    state <= IDLE;
                end
            endcase
        end
    end

    initial begin
        if(SIZE < 1) begin
            $error("sysController SIZE must be at least one");
        end
        if(INNER_DIM < 1) begin
            $error("sysController INNER_DIM must be at least one");
        end
        if(FIFO_DEPTH < 1) begin
            $error("sysController FIFO_DEPTH must be at least one");
        end
        if(REQUANT_SHIFT < 0 || REQUANT_SHIFT > 31) begin
            $error("sysController REQUANT_SHIFT must be between 0 and 31");
        end
        if(COMPUTE_CYCLES < 1) begin
            $error("sysController COMPUTE_CYCLES must be at least one");
        end
    end

endmodule

`default_nettype wire
