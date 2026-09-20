`timescale 1ns/1ps
`default_nettype none

module tb_primitives;
    logic clk = 1'b0;
    logic n_rst = 1'b0;
    always #5 clk = ~clk;

    logic counter_clear, count_en;
    logic [2:0] count_out;
    logic roll_flag;
    flexCounter #(.SIZE(3)) counter_i (
        .clk, .n_rst, .roll_val(3'd3), .clear(counter_clear), .count_en,
        .count_out, .roll_flag
    );

    logic sr_shift, sr_load, sr_in, sr_out;
    logic [7:0] sr_parallel_in, sr_parallel_out;
    flexSR #(.SIZE(8), .MSB_FIRST(1'b0)) sr_i (
        .clk, .n_rst, .shift_enable(sr_shift), .load_enable(sr_load),
        .serial_in(sr_in), .parallel_in(sr_parallel_in),
        .parallel_out(sr_parallel_out), .serial_out(sr_out)
    );

    logic fifo_wen, fifo_ren, fifo_full, fifo_empty, fifo_valid;
    logic [7:0] fifo_din, fifo_dout;
    asyncFIFO #(.DATA_WIDTH(8), .DEPTH(4)) fifo_i (
        .clk, .n_rst, .wen(fifo_wen), .ren(fifo_ren), .din(fifo_din),
        .dout(fifo_dout), .full(fifo_full), .empty(fifo_empty),
        .valid_read(fifo_valid)
    );

    logic bram_en, bram_we;
    logic [2:0] bram_addr;
    logic [31:0] bram_din, bram_dout;
    BRAMrw #(.DATA_WIDTH(32), .DEPTH(8)) bram_i (
        .clk, .n_rst, .en(bram_en), .we(bram_we), .addr(bram_addr),
        .din(bram_din), .dout(bram_dout)
    );

    logic pu_shift, pu_clear, pu_acc_en;
    logic signed [7:0] pu_int8, pu_right;
    logic signed [3:0] pu_int4, pu_down;
    logic signed [31:0] pu_acc;
    PU pu_i (
        .clk, .n_rst, .shift_en(pu_shift), .acc_clr(pu_clear),
        .acc_en(pu_acc_en), .int8_in(pu_int8), .int4_in(pu_int4),
        .right_pass(pu_right), .down_pass(pu_down), .accum_out(pu_acc)
    );

    task automatic tick;
        begin
            @(posedge clk);
            #1;
        end
    endtask

    task automatic fifo_write(input logic [7:0] value);
        begin
            @(negedge clk);
            fifo_din = value;
            fifo_wen = 1'b1;
            tick();
            fifo_wen = 1'b0;
        end
    endtask

    task automatic fifo_read_check(input logic [7:0] expected);
        begin
            @(negedge clk);
            fifo_ren = 1'b1;
            tick();
            if (!fifo_valid || fifo_dout !== expected)
                $fatal(1, "FIFO expected %0h, got %0h valid=%0b", expected, fifo_dout, fifo_valid);
            fifo_ren = 1'b0;
        end
    endtask

    initial begin
        counter_clear = 0;
        count_en = 0;
        sr_shift = 0;
        sr_load = 0;
        sr_in = 0;
        sr_parallel_in = 0;
        fifo_wen = 0;
        fifo_ren = 0;
        fifo_din = 0;
        bram_en = 0;
        bram_we = 0;
        bram_addr = 0;
        bram_din = 0;
        pu_shift = 0;
        pu_clear = 0;
        pu_acc_en = 0;
        pu_int8 = 0;
        pu_int4 = 0;

        repeat (2) tick();
        n_rst = 1'b1;
        tick();

        // Counter reaches terminal value, pulses, and wraps on the next edge.
        count_en = 1'b1;
        repeat (3) tick();
        if (count_out !== 3 || !roll_flag)
            $fatal(1, "counter terminal behavior incorrect: count=%0d roll=%0b", count_out, roll_flag);
        tick();
        if (count_out !== 0)
            $fatal(1, "counter failed to wrap");
        count_en = 1'b0;

        // LSB-first shift register.
        sr_parallel_in = 8'b1011_0010;
        sr_load = 1'b1;
        tick();
        sr_load = 1'b0;
        if (sr_out !== 1'b0)
            $fatal(1, "shift-register serial output incorrect");
        sr_shift = 1'b1;
        sr_in = 1'b0;
        tick();
        sr_shift = 1'b0;
        if (sr_parallel_out !== 8'b0101_1001)
            $fatal(1, "shift-register result incorrect: %b", sr_parallel_out);

        // FIFO ordering and full/empty flags.
        fifo_write(8'h11);
        fifo_write(8'h22);
        fifo_write(8'h33);
        fifo_write(8'h44);
        if (!fifo_full)
            $fatal(1, "FIFO did not assert full");

        // A simultaneous read/write while full must sustain one word/cycle.
        @(negedge clk);
        fifo_din = 8'h55;
        fifo_wen = 1'b1;
        fifo_ren = 1'b1;
        tick();
        if (!fifo_valid || fifo_dout !== 8'h11 || !fifo_full)
            $fatal(1, "FIFO full-throughput read/write failed");
        fifo_wen = 1'b0;
        fifo_ren = 1'b0;
        fifo_read_check(8'h22);
        fifo_read_check(8'h33);
        fifo_read_check(8'h44);
        fifo_read_check(8'h55);
        if (!fifo_empty)
            $fatal(1, "FIFO did not assert empty");

        // Write-first BRAM behavior followed by a synchronous read.
        @(negedge clk);
        bram_en = 1'b1;
        bram_we = 1'b1;
        bram_addr = 3'd5;
        bram_din = 32'hdead_beef;
        tick();
        if (bram_dout !== 32'hdead_beef)
            $fatal(1, "BRAM write-first output incorrect");
        bram_we = 1'b0;
        tick();
        if (bram_dout !== 32'hdead_beef)
            $fatal(1, "BRAM read output incorrect");
        bram_en = 1'b0;

        // Signed PE accumulation and operand forwarding.
        pu_clear = 1'b1;
        tick();
        pu_clear = 1'b0;
        pu_shift = 1'b1;
        pu_acc_en = 1'b1;
        pu_int8 = 8'sd3;
        pu_int4 = -4'sd2;
        tick();
        if (pu_acc !== -32'sd6 || pu_right !== 8'sd3 || pu_down !== -4'sd2)
            $fatal(1, "PE first signed MAC/forward failed");
        pu_int8 = -8'sd4;
        pu_int4 = 4'sd7;
        tick();
        if (pu_acc !== -32'sd34)
            $fatal(1, "PE accumulation failed: %0d", pu_acc);

        // Full signed operand limits catch accidental unsigned multiplication
        // and insufficient product width (-128 * -8 requires +1024).
        pu_clear = 1'b1;
        tick();
        pu_clear = 1'b0;
        pu_int8 = -8'sd128;
        pu_int4 = -4'sd8;
        tick();
        if (pu_acc !== 32'sd1024)
            $fatal(1, "PE signed limit product failed: %0d", pu_acc);
        pu_int8 = 8'sd127;
        pu_int4 = -4'sd8;
        tick();
        if (pu_acc !== 32'sd8)
            $fatal(1, "PE signed limit accumulation failed: %0d", pu_acc);

        $display("PASS: primitive RTL tests");
        $finish;
    end

endmodule

`default_nettype wire
