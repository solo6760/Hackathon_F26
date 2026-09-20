module kera_mem #(
    parameter int SIZE = 16,                   // fixed at 16: 16 INT4 = 2 words, 16 INT8 = 1 line
    parameter string W_FILE   = "w_fc1.hex",
    parameter string ACT_FILE = "act_fc1.hex"
) (
    input  logic clk,
    input  logic n_rst,

    // straight from kera_ctrl
    input  logic       tile_start,
    input  logic [5:0] tile_index,
    input  logic [3:0] group_index,
    input  logic       drain_start,

    // to the array: one K-step per cycle while feed_valid is high (16 cycles per tile)
    output logic                feed_valid,
    output logic signed [3:0]   vertInput  [SIZE-1:0],   // W[k][n]
    output logic signed [7:0]   horizInput [SIZE-1:0],   // X[m][k]

    // from the output FIFO: one token row per write
    input  logic                wr_valid,
    input  logic [SIZE*32-1:0]  wr_data,                 // [32n +: 32] = Y[m][16g+n]

    // readback of the finished 16 x 128 result, address = m*128 + channel
    input  logic [10:0]         res_addr,
    output logic [31:0]         res_data
);
    initial if (SIZE != 16) $error("kera_mem is written for SIZE = 16");

    logic [31:0]        wmem [0:1023];     // 32 tiles x 32 words, tile = 4*group + ktile
    logic [SIZE*8-1:0]  amem [0:63];       // one line per K index, byte m = X[m][k]
    logic [SIZE*32-1:0] omem [0:127];      // one line per (token, group): line = 8*m + g

    initial begin
        $readmemh(W_FILE, wmem);
        $readmemh(ACT_FILE, amem);
        for (int i = 0; i < 128; i++) omem[i] = '0;
    end

    // ---------------- read side ----------------
    logic       busy;
    logic [3:0] k;
    logic [5:0] tile_q;
    logic [3:0] group_q;

    logic [3:0] k_now;
    logic [5:0] tile_now;
    logic [3:0] group_now;
    logic       rd_en;

    // the first K-step is issued in the tile_start cycle, so data lands the cycle after
    assign k_now     = tile_start ? 4'd0 : k;
    assign tile_now  = tile_start ? tile_index : tile_q;
    assign group_now = tile_start ? group_index : group_q;
    assign rd_en     = tile_start | busy;

    always_ff @(posedge clk, negedge n_rst) begin
        if (!n_rst) begin
            busy       <= 1'b0;
            k          <= '0;
            tile_q     <= '0;
            group_q    <= '0;
            feed_valid <= 1'b0;
        end else begin
            feed_valid <= rd_en;
            if (tile_start) begin
                busy    <= 1'b1;
                k       <= 4'd1;
                tile_q  <= tile_index;
                group_q <= group_index;
            end else if (busy) begin
                k <= k + 4'd1;
                if (k == SIZE - 1) busy <= 1'b0;
            end
        end
    end

    // weight word = (4*group + ktile)*32 + 2*k ; the odd word (n = 8..15) is the next one
    logic [9:0] w_addr;
    logic [5:0] a_addr;
    assign w_addr = {group_now[2:0], tile_now[1:0], k_now, 1'b0};
    assign a_addr = {tile_now[1:0], k_now};

    logic [31:0]       w_lo, w_hi;
    logic [SIZE*8-1:0] a_line;

    always_ff @(posedge clk) begin
        if (rd_en) begin
            w_lo   <= wmem[w_addr];
            w_hi   <= wmem[w_addr | 10'd1];
            a_line <= amem[a_addr];
        end
    end

    always_comb begin
        for (int n = 0; n < 8; n++) begin
            vertInput[n]     = w_lo[4*n +: 4];
            vertInput[n + 8] = w_hi[4*n +: 4];
        end
        for (int m = 0; m < SIZE; m++)
            horizInput[m] = a_line[8*m +: 8];
    end

    // ---------------- write side ----------------
    logic [3:0] wr_row;
    logic [2:0] wr_grp;

    always_ff @(posedge clk, negedge n_rst) begin
        if (!n_rst) begin
            wr_row <= '0;
            wr_grp <= '0;
        end else if (drain_start) begin
            wr_row <= '0;
            wr_grp <= group_index[2:0];
        end else if (wr_valid) begin
            wr_row <= wr_row + 4'd1;
        end
    end

    always_ff @(posedge clk) begin
        if (wr_valid) omem[{wr_row, wr_grp}] <= wr_data;
    end

    // ---------------- readback ----------------
    logic [SIZE*32-1:0] res_line;
    logic [3:0]         res_word;

    always_ff @(posedge clk) begin
        res_line <= omem[res_addr[10:4]];
        res_word <= res_addr[3:0];
    end

    assign res_data = res_line[32*res_word +: 32];
endmodule
