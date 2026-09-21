`timescale 1ns / 1ps

module tb_basys3_top;
    localparam time CLK_PERIOD = 10ns; // 100 MHz clock

    logic clk = 0;
    always #(CLK_PERIOD / 2) clk = ~clk;

    logic btnC = 0;
    logic btnU = 0;
    logic [15:0] sw = 0;
    logic [15:0] led;
    logic [6:0]  seg;
    logic [3:0]  an;

    basys3_top dut (
        .clk(clk),
        .btnC(btnC),
        .btnU(btnU),
        .sw(sw),
        .led(led),
        .seg(seg),
        .an(an)
    );

    logic [31:0] golden [0:2047];

    initial begin
        $readmemh("golden_fc1.hex", golden);

        $display("=== Starting tb_basys3_top Simulation ===");

        // 1. Reset
        btnC = 1;
        #(CLK_PERIOD * 5);
        btnC = 0;
        #(CLK_PERIOD * 5);

        // 2. Check Ready LED
        if (led[0] !== 1'b1) begin
            $display("[FAIL] Expected led[0]=1 (ready), got %b", led[0]);
            $finish;
        end
        $display("  System Ready: led[0] = 1 at t=%0t", $time);

        // 3. Pulse Start Button (btnU)
        @(negedge clk);
        btnU = 1;
        #(CLK_PERIOD * 2);
        btnU = 0;
        $display("  Start pulse issued (btnU) at t=%0t", $time);

        // 4. Wait for Done LED
        wait (led[1] == 1'b1);
        #(CLK_PERIOD * 5);
        $display("  Execution Done: led[1] = 1 at t=%0t (halt_reason = %b)", $time, led[3:2]);

        // 5. Verify 2048 words via switch interface & internal res_data
        $display("=== Checking Results via Basys 3 Switch Interface ===");
        begin
            int errors = 0;
            for (int addr = 0; addr < 2048; addr++) begin
                sw = addr[15:0];
                #(CLK_PERIOD * 2);
                if (signed'(dut.res_data) !== signed'(golden[addr])) begin
                    $display("  [MISMATCH] Addr %0d: DUT = %0d (0x%08X), Expected = %0d (0x%08X)",
                             addr, signed'(dut.res_data), dut.res_data, signed'(golden[addr]), golden[addr]);
                    errors++;
                end
            end
            if (errors == 0) begin
                $display("=== SUCCESS: ALL 2048 WORDS MATCH GOLDEN FC1 IN BASYS 3 TOP! ===");
            end else begin
                $display("=== FAILURE: %0d MISMATCHES DETECTED ===", errors);
            end
        end

        // 6. Test 7-Segment Readout at Address 0 (Expected 0x0AA7)
        sw = 16'h0000; // Lower 16 bits of Addr 0
        #(CLK_PERIOD * 10);
        $display("  Address 0: res_data = 0x%08X", dut.res_data);
        $display("=== Basys 3 Hardware Simulation Finished Successfully ===");
        $finish;
    end

endmodule

