`timescale 1ns / 1ps

module tb_sysController;
    localparam int SIZE = 16;
    localparam time CLK_PERIOD = 10ns;

    logic clk = 0;
    logic n_rst = 0;
    always #(CLK_PERIOD / 2) clk = ~clk;

    logic tile_start = 0;
    logic drain_start = 0;
    logic [5:0] tile_index = 0;
    logic [3:0] group_index = 0;
    logic acc_clear = 0;
    logic acc_en = 0;
    logic [10:0] res_addr = 0;

    logic computer_active;
    logic drain_active;
    logic ready;
    logic [31:0] res_data;

    sysController #(
        .SIZE(SIZE)
    ) dut (
        .clk(clk),
        .n_rst(n_rst),
        .tile_start(tile_start),
        .drain_start(drain_start),
        .tile_index(tile_index),
        .acc_clear(acc_clear),
        .acc_en(acc_en),
        .group_index(group_index),
        .res_addr(res_addr),
        .computer_active(computer_active),
        .drain_active(drain_active),
        .ready(ready),
        .res_data(res_data)
    );

    // Golden memory for comparison
    logic [31:0] golden [0:2047];

    initial begin
        $readmemh("golden_fc1.hex", golden);

        // Reset
        n_rst = 0;
        #(CLK_PERIOD * 3);
        n_rst = 1;
        #(CLK_PERIOD * 2);

        $display("=== Starting sysController Simulation (All 8 Groups) ===");
        if (!ready) begin
            $display("[FAIL] Expected ready=1 out of reset, got %b", ready);
            $finish;
        end

        // Run all 8 Groups (4 tiles along K per group, then 1 drain per group)
        for (int g = 0; g < 8; g++) begin
            group_index = g[3:0];
            for (int t = 0; t < 4; t++) begin
                @(negedge clk);
                tile_start = 1;
                tile_index = t[5:0];
                acc_clear = (t == 0);
                acc_en = 1;
                @(negedge clk);
                tile_start = 0;
                acc_clear = 0;

                // Wait for tile computation to complete
                wait(ready == 1);
            end

            // Drain Group g
            @(negedge clk);
            drain_start = 1;
            acc_en = 0;
            @(negedge clk);
            drain_start = 0;

            wait(ready == 1);
            #(CLK_PERIOD * 2);
            $display("  Group %0d computed and drained at time %0t", g, $time);
        end

        // Check all 2048 words (16 tokens x 128 channels)
        $display("=== Checking Full FC1 Output (16 tokens x 128 channels = 2048 words) ===");
        begin
            int errors = 0;
            for (int m = 0; m < 16; m++) begin
                for (int ch = 0; ch < 128; ch++) begin
                    res_addr = m * 128 + ch;
                    #(CLK_PERIOD);
                    if (signed'(res_data) !== signed'(golden[m*128 + ch])) begin
                        $display("  [MISMATCH] Y[%0d][%0d]: DUT = %0d (0x%08X), Expected = %0d (0x%08X)",
                                 m, ch, signed'(res_data), res_data, signed'(golden[m*128+ch]), golden[m*128+ch]);
                        errors++;
                    end
                end
            end
            if (errors == 0) begin
                $display("=== SUCCESS: ALL 2048 WORDS MATCH GOLDEN FC1! ===");
            end else begin
                $display("=== FAILURE: %0d MISMATCHES DETECTED ===", errors);
            end
        end

        $display("=== Simulation Finished ===");
        $finish;
    end

    /*
    always @(posedge clk) begin
        if (dut.feed_valid) begin
            $display("  [FEED] t=%0t vert[0]=%0d horiz[0]=%0d", $time, dut.vertInput[0], dut.horizInput[0]);
        end
        if (dut.mem_wr_valid) begin
            $display("  [MEM_WR] t=%0t row=%0d data[31:0]=0x%08X (%0d)",
                     $time, dut.inst_kera_mem.wr_row, dut.mem_wr_data[31:0], signed'(dut.mem_wr_data[31:0]));
        end
    end
    */

endmodule

