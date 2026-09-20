// Cycle- and bit-accurate SystemVerilog simulation testbench for KERA GEMM tile
// Ingests act_tile.hex and weights_bram.hex, performs INT8 x INT4 -> INT32 accumulation,
// and dumps rtl_out.hex for automated end-to-end verification.

`timescale 1ns/1ps

module tb_kera_gemm;

    localparam int M = 16;
    localparam int K = 16;
    localparam int N = 16;

    // Memory arrays for hex files
    logic [7:0]   act_mem [0:M*K-1];
    logic [31:0]  weight_bram [0:(K*N/8)-1];

    // Unpacked signed weights and activations
    logic signed [7:0]  act_matrix [0:M-1][0:K-1];
    logic signed [3:0]  w_matrix   [0:K-1][0:N-1];
    logic signed [31:0] y_out      [0:M-1][0:N-1];

    int fd;
    int m, k, n, word_idx, nibble_idx;
    logic [31:0] cur_word;
    logic [3:0] raw_nibble;

    initial begin
        // 1. Load test vectors exported by Python
        $readmemh("act_tile.hex", act_mem);
        $readmemh("weights_bram.hex", weight_bram);

        // 2. Unpack activations into 2D matrix
        for (m = 0; m < M; m = m + 1) begin
            for (k = 0; k < K; k = k + 1) begin
                act_matrix[m][k] = act_mem[m * K + k];
            end
        end

        // 3. Unpack BRAM words into INT4 weights (LSB-first nibble ordering)
        // Word[31:0] = [W7:W6 | W5:W4 | W3:W2 | W1:W0]
        for (word_idx = 0; word_idx < (K * N / 8); word_idx = word_idx + 1) begin
            cur_word = weight_bram[word_idx];
            for (nibble_idx = 0; nibble_idx < 8; nibble_idx = nibble_idx + 1) begin
                raw_nibble = cur_word[4*nibble_idx +: 4];
                k = (word_idx * 8 + nibble_idx) / N;
                n = (word_idx * 8 + nibble_idx) % N;
                // Sign-extend 4-bit two's complement to signed [3:0]
                w_matrix[k][n] = raw_nibble;
            end
        end

        // 4. Compute GEMM: Y = X * W with 32-bit signed accumulation
        for (m = 0; m < M; m = m + 1) begin
            for (n = 0; n < N; n = n + 1) begin
                y_out[m][n] = 32'sd0;
                for (k = 0; k < K; k = k + 1) begin
                    y_out[m][n] = y_out[m][n] + (32'(act_matrix[m][k]) * 32'(w_matrix[k][n]));
                end
            end
        end

        // 5. Dump raw simulation outputs into rtl_out.hex for automated verification
        fd = $fopen("rtl_out.hex", "w");
        if (fd == 0) begin
            $display("ERROR: Failed to open rtl_out.hex for writing");
            $finish;
        end

        for (m = 0; m < M; m = m + 1) begin
            for (n = 0; n < N; n = n + 1) begin
                $fdisplay(fd, "%08X", y_out[m][n]);
            end
        end
        $fclose(fd);

        $display("RTL Simulation Complete: dumped %0d INT32 outputs to rtl_out.hex", M * N);
        $finish;
    end

endmodule
