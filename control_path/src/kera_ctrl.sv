// KERA control path: fetch, decode, sequence, halt
module kera_ctrl #(
    parameter int PC_W    = 8,
    parameter int TIMEOUT = 1024
) (
    input  logic            clk,
    input  logic            rst,

    output logic [PC_W-1:0] instr_addr,
    input  logic [15:0]     instr,

    input  logic            ready,

    output logic            tile_start,
    output logic [5:0]      tile_index,
    output logic [3:0]      group_index,
    output logic            last_tile,
    output logic            acc_clear,
    output logic            acc_en,
    output logic            drain_start,
    output logic [6:0]      channel,
    output logic            act_sel,
    output logic            wb_en,

    output logic            done,
    output logic [1:0]      halt_reason,
    output logic [PC_W-1:0] pc
);
    localparam logic [3:0]  OP_HALT    = 4'b0000;
    localparam logic [3:0]  OP_LOADRUN = 4'b0001;
    localparam logic [3:0]  OP_DRAIN   = 4'b0010;

    localparam logic [11:0] HALT_DELIBERATE = 12'hAAA;
    localparam logic [11:0] HALT_EMPTY      = 12'h000;

    localparam logic [1:0]  HR_DELIBERATE = 2'b00;
    localparam logic [1:0]  HR_EMPTY      = 2'b01;
    localparam logic [1:0]  HR_ILLEGAL    = 2'b10;
    localparam logic [1:0]  HR_TIMEOUT    = 2'b11;

    localparam int              WD_W     = $clog2(TIMEOUT + 1);
    localparam logic [WD_W-1:0] WD_LIMIT = WD_W'(TIMEOUT - 1);

    typedef enum logic [2:0] {
        S_BOOT, S_FETCH, S_EXEC, S_WAIT_LOW, S_WAIT_HIGH, S_HALT
    } state_t;

    state_t          state;
    logic [5:0]      tile_ctr;
    logic [3:0]      group_ctr;
    logic            first_of_group;
    logic            op_is_tile;
    logic            op_last;
    logic [WD_W-1:0] wd;

    logic [3:0]  opcode;
    logic [11:0] payload;
    logic        in_flight;
    logic        drain_ok;
    logic        wd_expired;

    assign opcode  = instr[15:12];
    assign payload = instr[11:0];

    assign in_flight  = (state == S_WAIT_LOW) || (state == S_WAIT_HIGH);
    assign instr_addr = in_flight ? pc + PC_W'(1) : pc;  // fetch the next word while the op runs

    assign drain_ok = ({1'b0, payload[11:5]} == {group_ctr, 4'b0000});

    assign wd_expired = (wd == WD_LIMIT);

    always_ff @(posedge clk) begin
        if (rst) begin
            state          <= S_BOOT;
            pc             <= '0;
            tile_ctr       <= '0;
            group_ctr      <= '0;
            first_of_group <= 1'b1;
            op_is_tile     <= 1'b0;
            op_last        <= 1'b0;
            wd             <= '0;
            tile_start     <= 1'b0;
            tile_index     <= '0;
            group_index    <= '0;
            last_tile      <= 1'b0;
            acc_clear      <= 1'b1;   // accumulator bank comes out of reset cleared
            acc_en         <= 1'b0;
            drain_start    <= 1'b0;
            channel        <= '0;
            act_sel        <= 1'b0;
            wb_en          <= 1'b0;
            done           <= 1'b0;
            halt_reason    <= HR_DELIBERATE;
        end else begin
            tile_start  <= 1'b0;
            drain_start <= 1'b0;
            acc_clear   <= 1'b0;

            case (state)
                S_BOOT: begin
                    if (ready) begin
                        wd    <= '0;
                        state <= S_FETCH;
                    end else if (wd_expired) begin
                        done        <= 1'b1;
                        halt_reason <= HR_TIMEOUT;
                        state       <= S_HALT;
                    end else begin
                        wd <= wd + WD_W'(1);
                    end
                end

                S_FETCH: state <= S_EXEC;

                S_EXEC: begin
                    case (opcode)
                        OP_LOADRUN, OP_DRAIN: begin
                            if (opcode == OP_DRAIN && !drain_ok) begin
                                done        <= 1'b1;
                                halt_reason <= HR_ILLEGAL;
                                state       <= S_HALT;
                            end else if (ready) begin
                                wd    <= '0;
                                state <= S_WAIT_LOW;
                                if (opcode == OP_LOADRUN) begin
                                    tile_start  <= 1'b1;
                                    tile_index  <= tile_ctr;
                                    group_index <= group_ctr;
                                    last_tile   <= payload[11];
                                    acc_clear   <= first_of_group;
                                    acc_en      <= 1'b1;
                                    op_is_tile  <= 1'b1;
                                    op_last     <= payload[11];
                                end else begin
                                    drain_start <= 1'b1;
                                    group_index <= group_ctr;
                                    channel     <= payload[11:5];
                                    act_sel     <= payload[4];
                                    wb_en       <= 1'b1;
                                    op_is_tile  <= 1'b0;
                                end
                            end else if (wd_expired) begin
                                done        <= 1'b1;
                                halt_reason <= HR_TIMEOUT;
                                state       <= S_HALT;
                            end else begin
                                wd <= wd + WD_W'(1);
                            end
                        end

                        OP_HALT: begin
                            done  <= 1'b1;
                            state <= S_HALT;
                            if (payload == HALT_DELIBERATE)  halt_reason <= HR_DELIBERATE;
                            else if (payload == HALT_EMPTY)  halt_reason <= HR_EMPTY;
                            else                             halt_reason <= HR_ILLEGAL;
                        end

                        default: begin  // 0011 (reserved) and 0100-1111
                            done        <= 1'b1;
                            halt_reason <= HR_ILLEGAL;
                            state       <= S_HALT;
                        end
                    endcase
                end

                S_WAIT_LOW, S_WAIT_HIGH: begin
                    if (state == S_WAIT_HIGH && ready) begin
                        acc_en    <= 1'b0;
                        wb_en     <= 1'b0;
                        last_tile <= 1'b0;
                        if (op_is_tile) begin
                            tile_ctr       <= op_last ? '0 : tile_ctr + 6'd1;
                            first_of_group <= 1'b0;
                        end else begin
                            group_ctr      <= group_ctr + 4'd1;
                            first_of_group <= 1'b1;
                        end
                        wd    <= '0;
                        pc    <= pc + PC_W'(1);
                        state <= S_EXEC;
                    end else if (wd_expired) begin
                        acc_en      <= 1'b0;
                        wb_en       <= 1'b0;
                        last_tile   <= 1'b0;
                        done        <= 1'b1;
                        halt_reason <= HR_TIMEOUT;
                        state       <= S_HALT;
                    end else begin
                        wd <= wd + WD_W'(1);
                        if (state == S_WAIT_LOW && !ready) state <= S_WAIT_HIGH;
                    end
                end

                S_HALT: ;  // frozen until reset

                default: begin
                    done        <= 1'b1;
                    halt_reason <= HR_ILLEGAL;
                    state       <= S_HALT;
                end
            endcase
        end
    end

endmodule
