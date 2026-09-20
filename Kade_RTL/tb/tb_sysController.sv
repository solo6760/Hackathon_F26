`timescale 1ns/1ps
`default_nettype none

module tb_sysController;
    localparam int SIZE = 4;
    localparam int INNER_DIM = 7;
    localparam int SHIFT = 2;
    localparam int COMPUTE_CYCLES = INNER_DIM + 2*SIZE - 2;

    logic clk = 1'b0;
    logic n_rst = 1'b0;
    always #5 clk = ~clk;

    logic tile_start, drain_start, fifo_ren;
    logic signed [3:0] vert_input [0:SIZE-1];
    logic signed [7:0] horiz_input [0:SIZE-1];
    logic signed [7:0] fifo_dout;
    logic fifo_empty, fifo_full, fifo_valid;
    logic compute_active, drain_active, tile_done, drain_done;

    logic signed [7:0] matrix_a [0:SIZE-1][0:INNER_DIM-1];
    logic signed [3:0] matrix_b [0:INNER_DIM-1][0:SIZE-1];
    integer expected [0:SIZE-1][0:SIZE-1];
    integer received;
    integer row, col, k, t, index;
    integer scaled;

    sysController #(
        .SIZE(SIZE),
        .INNER_DIM(INNER_DIM),
        .FIFO_DEPTH(4), // Deliberately small to exercise FIFO backpressure.
        .REQUANT_SHIFT(SHIFT)
    ) dut (
        .clk, .n_rst, .tile_start, .drain_start,
        .vert_input, .horiz_input, .fifo_ren,
        .fifo_dout, .fifo_empty, .fifo_full, .fifo_valid,
        .compute_active, .drain_active, .tile_done, .drain_done
    );

    function automatic integer requantize(input integer value);
        integer shifted;
        begin
            if (value < 0)
                shifted = (value + (1 << (SHIFT-1)) - 1) >>> SHIFT;
            else
                shifted = (value + (1 << (SHIFT-1))) >>> SHIFT;
            if (shifted > 127)
                requantize = 127;
            else if (shifted < -128)
                requantize = -128;
            else
                requantize = shifted;
        end
    endfunction

    task automatic clear_edges;
        integer i;
        begin
            for (i = 0; i < SIZE; i++) begin
                horiz_input[i] = '0;
                vert_input[i] = '0;
            end
        end
    endtask

    initial begin
        tile_start = 0;
        drain_start = 0;
        fifo_ren = 0;
        clear_edges();

        // A non-square K dimension verifies projection-sized tiles rather than
        // only the simpler SIZE x SIZE x SIZE case. Row zero and columns zero
        // and one deliberately force positive and negative saturation.
        for (row = 0; row < SIZE; row++) begin
            for (k = 0; k < INNER_DIM; k++) begin
                if (row == 0)
                    matrix_a[row][k] = 8'sd100;
                else
                    matrix_a[row][k] = ((row*17 + k*11) % 81) - 40;
            end
        end
        for (k = 0; k < INNER_DIM; k++) begin
            for (col = 0; col < SIZE; col++) begin
                if (col == 0)
                    matrix_b[k][col] = 4'sd7;
                else if (col == 1)
                    matrix_b[k][col] = -4'sd7;
                else
                    matrix_b[k][col] = ((k*5 + col*3) % 15) - 7;
            end
        end

        for (row = 0; row < SIZE; row++) begin
            for (col = 0; col < SIZE; col++) begin
                expected[row][col] = 0;
                for (k = 0; k < INNER_DIM; k++)
                    expected[row][col] = expected[row][col] + matrix_a[row][k] * matrix_b[k][col];
            end
        end

        repeat (3) @(posedge clk);
        n_rst = 1'b1;

        // Exact signed requantization boundaries, including negative ties.
        if ($signed(dut.requantize_int8(32'sd6)) !== 8'sd2)
            $fatal(1, "positive tie rounding failed");
        if ($signed(dut.requantize_int8(-32'sd6)) !== -8'sd2)
            $fatal(1, "negative tie rounding failed");
        if ($signed(dut.requantize_int8(32'sd4096)) !== 8'sd127)
            $fatal(1, "positive saturation failed");
        if ($signed(dut.requantize_int8(-32'sd4096)) !== -8'sd128)
            $fatal(1, "negative saturation failed");

        @(negedge clk);
        tile_start = 1'b1;
        @(negedge clk);
        tile_start = 1'b0;

        wait (compute_active);
        for (t = 0; t < COMPUTE_CYCLES; t++) begin
            @(negedge clk);
            for (row = 0; row < SIZE; row++) begin
                k = t - row;
                horiz_input[row] = (k >= 0 && k < INNER_DIM) ? matrix_a[row][k] : '0;
            end
            for (col = 0; col < SIZE; col++) begin
                k = t - col;
                vert_input[col] = (k >= 0 && k < INNER_DIM) ? matrix_b[k][col] : '0;
            end
        end
        @(posedge clk);
        #1;
        clear_edges();
        if (!tile_done)
            $fatal(1, "controller failed to assert tile_done");

        @(negedge clk);
        drain_start = 1'b1;
        @(negedge clk);
        drain_start = 1'b0;

        // Hold the consumer off until the small FIFO fills, then verify that
        // drain state stalls safely and resumes without losing ordering.
        wait (fifo_full);
        repeat (2) begin
            @(posedge clk);
            #1;
            if (!fifo_full || !drain_active)
                $fatal(1, "drain did not hold correctly under backpressure");
        end
        @(negedge clk);
        fifo_ren = 1'b1;

        received = 0;
        while (received < SIZE*SIZE) begin
            @(posedge clk);
            #1;
            if (fifo_valid) begin
                row = received / SIZE;
                col = received % SIZE;
                scaled = requantize(expected[row][col]);
                if ($signed(fifo_dout) !== scaled)
                    $fatal(1,
                        "output[%0d][%0d]: expected %0d (acc %0d), got %0d",
                        row, col, scaled, expected[row][col], $signed(fifo_dout));
                received = received + 1;
            end
        end

        @(negedge clk);
        fifo_ren = 1'b0;
        repeat (2) @(posedge clk);
        if (!fifo_empty)
            $fatal(1, "FIFO not empty after reading complete tile");

        $display("PASS: systolic tile, requantization, drain, and FIFO tests");
        $finish;
    end

    initial begin
        #10000;
        $fatal(1, "testbench timeout");
    end

endmodule

`default_nettype wire
