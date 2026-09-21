module basys3_top (
    input  logic        clk,         // 100MHz onboard oscillator (pin W5)
    input  logic        btnC,        // Center button: System Reset (active-high)
    input  logic        btnU,        // Up button: Run inference
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [15:0] sw,          // sw[10:0]: res_addr (0..2047), sw[15]: 0=lower 16b, 1=upper 16b
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [15:0] led,         // Status & monitoring LEDs
    output logic [6:0]  seg,         // 7-segment cathode signals (active-low)
    output logic [3:0]  an           // 7-segment anode signals (active-low)
);

    // -------------------------------------------------------------
    // Button Synchronizers and Debounce/Edge Detection
    // -------------------------------------------------------------
    logic rst_sync;
    logic btnC_q, btnC_q2;
    logic btnU_q, btnU_q2;
    logic run_enable;

    always_ff @(posedge clk) begin
        btnC_q   <= btnC;
        btnC_q2  <= btnC_q;
        rst_sync <= btnC_q2;

        btnU_q   <= btnU;
        btnU_q2  <= btnU_q;

        if (rst_sync) begin
            run_enable <= 1'b0;
        end else if (btnU_q && !btnU_q2) begin
            run_enable <= 1'b1;
        end
    end

    logic ctrl_rst;
    assign ctrl_rst = rst_sync || !run_enable;

    // -------------------------------------------------------------
    // Instruction Memory (BRAM initialized with fc1.hex)
    // -------------------------------------------------------------
    logic [7:0]  instr_addr;
    logic [15:0] instr;
    (* ram_style = "block" *) logic [15:0] prog_mem [0:255];

    initial begin
        for (int i = 0; i < 256; i++) prog_mem[i] = '0;
        $readmemh("fc1.hex", prog_mem);
    end

    always_ff @(posedge clk) begin
        instr <= prog_mem[instr_addr];
    end

    // -------------------------------------------------------------
    // Interconnect Signals between kera_ctrl & sysController
    // -------------------------------------------------------------
    logic ready, tile_start, drain_start, acc_clear, acc_en;
    logic [5:0] tile_index;
    logic [3:0] group_index;
    logic done;
    logic [1:0] halt_reason;
    logic [31:0] res_data;
    logic computer_active, drain_active;

    // Unused control signals from kera_ctrl
    /* verilator lint_off UNUSEDSIGNAL */
    logic last_tile, act_sel, wb_en;
    logic [6:0] channel;
    logic [7:0] pc;
    /* verilator lint_on UNUSEDSIGNAL */

    // -------------------------------------------------------------
    // Control Path Module
    // -------------------------------------------------------------
    kera_ctrl #(
        .PC_W(8),
        .TIMEOUT(1024)
    ) u_ctrl (
        .clk(clk),
        .rst(ctrl_rst),
        .instr_addr(instr_addr),
        .instr(instr),
        .ready(ready),
        .tile_start(tile_start),
        .tile_index(tile_index),
        .group_index(group_index),
        .last_tile(last_tile),
        .acc_clear(acc_clear),
        .acc_en(acc_en),
        .drain_start(drain_start),
        .channel(channel),
        .act_sel(act_sel),
        .wb_en(wb_en),
        .done(done),
        .halt_reason(halt_reason),
        .pc(pc)
    );

    // -------------------------------------------------------------
    // Systolic Controller, Memory & Datapath
    // -------------------------------------------------------------
    sysController #(
        .SIZE(16)
    ) u_sys (
        .clk(clk),
        .n_rst(!rst_sync),
        .tile_start(tile_start),
        .drain_start(drain_start),
        .tile_index(tile_index),
        .acc_clear(acc_clear),
        .acc_en(acc_en),
        .group_index(group_index),
        .res_addr(sw[10:0]),
        .computer_active(computer_active),
        .drain_active(drain_active),
        .ready(ready),
        .res_data(res_data)
    );

    // -------------------------------------------------------------
    // LED Indicators
    // -------------------------------------------------------------
    assign led[0]    = ready;
    assign led[1]    = done;
    assign led[3:2]  = halt_reason;
    assign led[4]    = computer_active;
    assign led[5]    = drain_active;
    assign led[15:6] = sw[9:0]; // Echo lower address bits onto LEDs

    // -------------------------------------------------------------
    // 4-Digit 7-Segment Hex Display Controller
    // -------------------------------------------------------------
    logic [19:0] refresh_counter = 0;
    always_ff @(posedge clk) refresh_counter <= refresh_counter + 1'b1;

    logic [1:0] digit_sel;
    assign digit_sel = refresh_counter[19:18];

    // Select upper or lower 16 bits via sw[15]
    logic [15:0] display_val;
    assign display_val = sw[15] ? res_data[31:16] : res_data[15:0];

    logic [3:0] hex_nibble;
    always_comb begin
        case (digit_sel)
            2'b00: begin an = 4'b1110; hex_nibble = display_val[3:0];   end
            2'b01: begin an = 4'b1101; hex_nibble = display_val[7:4];   end
            2'b10: begin an = 4'b1011; hex_nibble = display_val[11:8];  end
            2'b11: begin an = 4'b0111; hex_nibble = display_val[15:12]; end
        endcase
    end

    // 7-segment hex decoder (active-low cathodes)
    always_comb begin
        case (hex_nibble)
            4'h0: seg = 7'b1000000;
            4'h1: seg = 7'b1111001;
            4'h2: seg = 7'b0100100;
            4'h3: seg = 7'b0110000;
            4'h4: seg = 7'b0011001;
            4'h5: seg = 7'b0010010;
            4'h6: seg = 7'b0000010;
            4'h7: seg = 7'b1111000;
            4'h8: seg = 7'b0000000;
            4'h9: seg = 7'b0010000;
            4'hA: seg = 7'b0001000;
            4'hB: seg = 7'b0000011;
            4'hC: seg = 7'b1000110;
            4'hD: seg = 7'b0100001;
            4'hE: seg = 7'b0000110;
            4'hF: seg = 7'b0001110;
        endcase
    end

endmodule
