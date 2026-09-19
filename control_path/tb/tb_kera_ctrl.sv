// Self-checking testbench for kera_ctrl, running the fc1 program
module tb_kera_ctrl;

    localparam int    PC_W       = 8;
    localparam int    TIMEOUT    = 64;
    localparam int    MAX_CYCLES = 20000;
    localparam string PROG       = "prog/fc1.hex";

    localparam int    K_TILES    = 4;
    localparam int    GROUPS     = 8;
    localparam int    N_TILE     = K_TILES * GROUPS;
    localparam int    N_DRAIN    = GROUPS;
    localparam int    N_OPS      = N_TILE + N_DRAIN;
    localparam int    HALT_PC    = N_OPS;

    logic clk = 1'b0;
    logic rst = 1'b1;
    always #5 clk = ~clk;

    logic [PC_W-1:0] instr_addr;
    logic [15:0]     instr;
    logic            ready;
    logic            tile_start, last_tile, acc_clear, acc_en;
    logic            drain_start, act_sel, wb_en, done;
    logic [5:0]      tile_index;
    logic [3:0]      group_index;
    logic [6:0]      channel;
    logic [1:0]      halt_reason;
    logic [PC_W-1:0] pc;

    kera_ctrl #(.PC_W(PC_W), .TIMEOUT(TIMEOUT)) DUT (.*);

    logic [15:0] mem [0:(1<<PC_W)-1];
    always_ff @(posedge clk) instr <= mem[instr_addr];

    int busy_tile, busy_drain;
    int dp_cnt;
    int op_num;
    int stall_at;
    int stall_len;
    int drop_pc;
    bit dp_ignore;
    bit dp_hang;
    logic dp_ready;

    assign ready = dp_ready && !(drop_pc >= 0 && int'(pc) == drop_pc);

    always_ff @(posedge clk) begin
        if (rst) begin
            dp_ready <= 1'b1;
            dp_cnt   <= 0;
            op_num   <= 0;
        end else if (dp_cnt > 0) begin
            if (!dp_hang) begin
                dp_cnt <= dp_cnt - 1;
                if (dp_cnt == 1) dp_ready <= 1'b1;
            end
        end else if ((tile_start || drain_start) && !dp_ignore) begin
            dp_ready <= 1'b0;
            dp_cnt   <= (tile_start ? busy_tile : busy_drain)
                      + ((op_num == stall_at) ? stall_len : 0);
            op_num   <= op_num + 1;
        end
    end

    int cyc;
    always_ff @(posedge clk) cyc <= rst ? 0 : cyc + 1;

    int          errors;
    int          exp_ops;
    int          n_tile, n_drain;
    int          exp_tile_ctr;
    int          exp_group;
    bit          exp_first;
    bit          prev_strobe;
    bit          prev_ready;
    bit          op_tile;
    bit          early_reported;
    bit          inject_done_high, inject_done_low;
    int          k;
    logic [15:0] w;
    logic        done_obs;

    int          walk_g [0:255];
    int          walk_t [0:255];

    assign done_obs = inject_done_high ? 1'b1 : (inject_done_low ? 1'b0 : done);

    bit quiet;

    task automatic fail(input string msg);
        errors++;
        if (!quiet) $display("  [FAIL t=%0t] %s", $time, msg);
    endtask

    always @(negedge clk) begin
        if (rst) begin
            n_tile         = 0;
            n_drain        = 0;
            exp_tile_ctr   = 0;
            exp_group      = 0;
            exp_first      = 1'b1;
            prev_strobe    = 1'b0;
            prev_ready     = 1'b1;
            op_tile        = 1'b0;
            early_reported = 1'b0;
        end else begin
            k = n_tile + n_drain;

            if (tile_start && drain_start)
                fail("tile_start and drain_start asserted together");
            if ((tile_start || drain_start) && prev_strobe)
                fail("strobe held longer than one cycle");
            if ((tile_start || drain_start) && !prev_ready)
                fail("strobe issued while ready LOW");

            if (tile_start) begin
                w = mem[k];
                if (w[15:12] != 4'b0001)          fail($sformatf("tile_start on word %0d = %h", k, w));
                if (int'(pc) != k)                fail($sformatf("pc %0d, expected %0d", pc, k));
                if (int'(tile_index) != exp_tile_ctr)
                    fail($sformatf("tile_index %0d, expected %0d (word %0d)", tile_index, exp_tile_ctr, k));
                if (int'(group_index) != exp_group)
                    fail($sformatf("group_index %0d, expected %0d (word %0d)", group_index, exp_group, k));
                if (last_tile != w[11])           fail($sformatf("last_tile %b on word %0d", last_tile, k));
                if (acc_clear != exp_first)       fail($sformatf("acc_clear %b, expected %b (word %0d)", acc_clear, exp_first, k));
                if (!acc_en)                      fail("acc_en LOW with tile_start");
                if (wb_en)                        fail("wb_en HIGH with tile_start");
                walk_g[n_tile] = int'(group_index);
                walk_t[n_tile] = int'(tile_index);
                exp_tile_ctr = w[11] ? 0 : exp_tile_ctr + 1;
                exp_first    = 1'b0;
                op_tile      = 1'b1;
                n_tile++;
            end

            if (drain_start) begin
                w = mem[k];
                if (w[15:12] != 4'b0010)          fail($sformatf("drain_start on word %0d = %h", k, w));
                if (int'(pc) != k)                fail($sformatf("pc %0d, expected %0d", pc, k));
                if (channel != w[11:5])           fail($sformatf("channel %0d, expected %0d (word %0d)", channel, w[11:5], k));
                if (int'(channel) != 16 * exp_group)
                    fail($sformatf("drained channel %0d in group %0d", channel, exp_group));
                if (int'(group_index) != exp_group)
                    fail($sformatf("group_index %0d on DRAIN, expected %0d", group_index, exp_group));
                if (act_sel != w[4])              fail($sformatf("act_sel %b on word %0d", act_sel, k));
                if (!wb_en)                       fail("wb_en LOW with drain_start");
                if (acc_en)                       fail("acc_en HIGH with drain_start");
                exp_group++;
                exp_first = 1'b1;
                op_tile   = 1'b0;
                n_drain++;
            end

            if (!ready && !done && (n_tile + n_drain) > 0 && drop_pc < 0) begin
                if (op_tile  && (!acc_en ||  wb_en)) fail("acc_en/wb_en wrong while LOADRUN in flight");
                if (!op_tile && ( acc_en || !wb_en)) fail("acc_en/wb_en wrong while DRAIN in flight");
            end

            if (done && (tile_start || drain_start || acc_en || wb_en))
                fail("datapath activity after halt");

            if (done_obs && (n_tile + n_drain) < exp_ops && !early_reported) begin
                fail($sformatf("done HIGH after %0d of %0d operations", n_tile + n_drain, exp_ops));
                early_reported = 1'b1;
            end

            prev_strobe = tile_start || drain_start;
            prev_ready  = ready;
        end
    end

    task automatic defaults();
        busy_tile        = 3;
        busy_drain       = 3;
        dp_ignore        = 1'b0;
        dp_hang          = 1'b0;
        stall_at         = -1;
        stall_len        = 0;
        drop_pc          = -1;
        inject_done_high = 1'b0;
        inject_done_low  = 1'b0;
    endtask

    task automatic clear_mem();
        for (int i = 0; i < (1 << PC_W); i++) mem[i] = 16'h0000;
    endtask

    task automatic load_fc1();
        clear_mem();
        $readmemh(PROG, mem);
    endtask

    task automatic start_test(input string name, input int ops);
        @(negedge clk);
        rst     = 1'b1;
        exp_ops = ops;
        $display("TEST: %s", name);
        repeat (2) @(posedge clk);
        @(negedge clk);
        if (tile_start || drain_start || acc_en || wb_en || last_tile || act_sel || done ||
            !acc_clear || tile_index != 0 || group_index != 0 || channel != 0 ||
            halt_reason != 2'b00 || pc != 0)
            fail("reset values do not match control table section 5");
        rst = 1'b0;
    endtask

    task automatic run_until_done(output int cycles);
        do @(negedge clk); while (!done_obs && cyc < MAX_CYCLES);
        if (cyc >= MAX_CYCLES) fail("gave up waiting for done");
        cycles = cyc;
    endtask

    task automatic expect_halt(input logic [1:0] reason, input int at_pc,
                               input int ntile, input int ndrain);
        if (!done)                              fail("done not set");
        if (halt_reason != reason)              fail($sformatf("halt_reason %b, expected %b", halt_reason, reason));
        if (int'(pc) != at_pc)                  fail($sformatf("halted at pc %0d, expected %0d", pc, at_pc));
        if (n_tile != ntile || n_drain != ndrain)
            fail($sformatf("saw %0d tiles / %0d drains, expected %0d / %0d", n_tile, n_drain, ntile, ndrain));
    endtask

    // 3 cycles to the first strobe, then busy + 3 per op
    function automatic int predict(input int bt, input int bd);
        return 3 + N_TILE * (bt + 3) + N_DRAIN * (bd + 3);
    endfunction

    initial begin
        int base_cycles, stall_cycles, c, e0;
        bit caught_high, caught_low, walk_ok;

        $dumpfile("waveform.fst");
        $dumpvars;
        errors = 0;
        quiet  = 1'b0;

        defaults(); load_fc1();
        start_test("fc1 program (64 -> 128, 16x16x16 tiles)", N_OPS);
        run_until_done(base_cycles);
        expect_halt(2'b00, HALT_PC, N_TILE, N_DRAIN);
        $display("  measured %0d cycles, predicted %0d (busy 3/3)", base_cycles, predict(3, 3));
        if (base_cycles != predict(3, 3)) fail("cycle count does not match the prediction");

        if (walk_g[0]  != 0 || walk_t[0]  != 0) fail($sformatf("first tile (%0d,%0d), expected (0,0)", walk_g[0],  walk_t[0]));
        if (walk_g[17] != 4 || walk_t[17] != 1) fail($sformatf("tile 17 (%0d,%0d), expected (4,1)",  walk_g[17], walk_t[17]));
        if (walk_g[31] != 7 || walk_t[31] != 3) fail($sformatf("last tile (%0d,%0d), expected (7,3)", walk_g[31], walk_t[31]));
        walk_ok = 1'b1;
        for (int i = 0; i < N_TILE; i++)
            if (walk_g[i] != i / K_TILES || walk_t[i] != i % K_TILES) walk_ok = 1'b0;
        if (!walk_ok) fail("tile/group walk does not match (i / 4, i % 4)");

        defaults(); load_fc1(); busy_tile = 16; busy_drain = 16;
        start_test("fc1 latency at 16-cycle tiles and drains", N_OPS);
        run_until_done(c);
        expect_halt(2'b00, HALT_PC, N_TILE, N_DRAIN);
        $display("  measured %0d cycles, predicted %0d", c, predict(16, 16));
        if (c != predict(16, 16)) fail("cycle count does not match the prediction");

        defaults(); load_fc1(); stall_at = 10; stall_len = 17;
        start_test("stall of 17 cycles on operation 10", N_OPS);
        run_until_done(stall_cycles);
        expect_halt(2'b00, HALT_PC, N_TILE, N_DRAIN);
        if (stall_cycles - base_cycles != 17)
            fail($sformatf("stall added %0d cycles, expected exactly 17", stall_cycles - base_cycles));

        defaults(); clear_mem();
        mem[0] = 16'h1800; mem[1] = 16'h2000;
        mem[2] = 16'h1800; mem[3] = 16'h2200;
        mem[4] = 16'h0AAA;
        start_test("single-tile groups (first tile is also LAST)", 4);
        run_until_done(c);
        expect_halt(2'b00, 4, 2, 2);

        defaults(); load_fc1(); mem[9] = 16'h2600;
        start_test("DRAIN names the wrong block (channel 48 in group 1)", 9);
        run_until_done(c);
        expect_halt(2'b10, 9, 8, 1);

        defaults(); load_fc1(); mem[4] = 16'h2020;
        start_test("DRAIN channel not on a block boundary", 4);
        run_until_done(c);
        expect_halt(2'b10, 4, 4, 0);

        defaults(); load_fc1();
        mem[40] = 16'h1800; mem[41] = 16'h2000; mem[42] = 16'h0AAA;
        start_test("ninth group cannot reuse channel 0", N_OPS + 1);
        run_until_done(c);
        expect_halt(2'b10, 41, N_TILE + 1, N_DRAIN);

        defaults(); load_fc1(); mem[5] = 16'h4000;
        start_test("illegal opcode 0100 at word 5", 5);
        run_until_done(c);
        expect_halt(2'b10, 5, 4, 1);

        defaults(); load_fc1(); mem[8] = 16'h3000;
        start_test("reserved opcode 0011 at word 8", 8);
        run_until_done(c);
        expect_halt(2'b10, 8, 7, 1);

        defaults(); load_fc1(); mem[HALT_PC] = 16'h0123;
        start_test("malformed HALT payload 0x123", N_OPS);
        run_until_done(c);
        expect_halt(2'b10, HALT_PC, N_TILE, N_DRAIN);

        defaults(); clear_mem();
        start_test("unprogrammed memory", 0);
        run_until_done(c);
        expect_halt(2'b01, 0, 0, 0);

        defaults(); load_fc1(); mem[HALT_PC] = 16'h0000;
        start_test("program with no HALT runs off the end", N_OPS);
        run_until_done(c);
        expect_halt(2'b01, HALT_PC, N_TILE, N_DRAIN);

        defaults(); load_fc1(); dp_ignore = 1'b1;
        start_test("datapath never accepts a strobe (ready stuck HIGH)", 0);
        run_until_done(c);
        expect_halt(2'b11, 0, 1, 0);

        defaults(); load_fc1(); dp_hang = 1'b1;
        start_test("datapath never finishes (ready stuck LOW)", 0);
        run_until_done(c);
        expect_halt(2'b11, 0, 1, 0);

        defaults(); load_fc1(); drop_pc = 0;
        start_test("ready LOW out of reset (hang in BOOT)", 0);
        run_until_done(c);
        expect_halt(2'b11, 0, 0, 0);

        defaults(); load_fc1(); drop_pc = 3;
        start_test("ready LOW with nothing in flight (hang in EXEC)", 3);
        run_until_done(c);
        expect_halt(2'b11, 3, 3, 0);

        e0 = errors;
        quiet = 1'b1;
        defaults(); load_fc1(); inject_done_high = 1'b1;
        start_test("NEGATIVE: done stuck HIGH (must be caught)", N_OPS);
        run_until_done(c);
        caught_high = (errors > e0);
        errors = e0;

        defaults(); load_fc1(); inject_done_low = 1'b1;
        start_test("NEGATIVE: done stuck LOW (must be caught)", N_OPS);
        run_until_done(c);
        caught_low = (errors > e0);
        errors = e0;
        quiet = 1'b0;

        if (!caught_high) begin errors++; $display("  [FAIL] TB passed with done stuck HIGH - the TB is broken"); end
        else $display("  negative test OK: done stuck HIGH was caught");
        if (!caught_low)  begin errors++; $display("  [FAIL] TB passed with done stuck LOW - the TB is broken"); end
        else $display("  negative test OK: done stuck LOW was caught");

        $display("");
        if (errors == 0) $display("PASSED: all KERA control-path tests");
        else             $display("FAILED: %0d error(s)", errors);
        $finish;
    end

endmodule
