module asyncFIFO # (
    I_SIZE = 8,
    O_SIZE = 8,
    WIDTH = 4
) (
    input logic clk,
    input logic n_rst,
    input logic wen,
    input logic ren,
    input logic [I_SIZE-1:0] din,
    output logic [O_SIZE-1:0] dout,
    output logic full,
    output logic empty,
    output logic valid_read
);

    logic [I_SIZE-1:0] regs [WIDTH-1:0];
    logic [I_SIZE-1:0] next_regs [WIDTH-1:0];
    logic [$clog2(WIDTH):0] rp, wp, next_rp, next_wp; // MSB is a flag for wrap over 
    logic [I_SIZE-1:0] fOut, nextf;

    always_ff @(posedge clk, negedge n_rst) begin
        if(!n_rst) begin
            regs <= '{default: '0};
            rp <= '0;
            wp <= '0;
            fOut <= '0;
        end else begin
            regs <= next_regs;
            rp <= next_rp;
            wp <= next_wp;
            fOut <= nextf;
        end
    end

    always_comb begin
        empty = rp == wp;
        full = (rp[$clog2(WIDTH)] != wp[$clog2(WIDTH)] && rp[$clog2(WIDTH) - 1:0] == wp[$clog2(WIDTH) - 1:0]);

        
        next_regs = regs;
        next_regs[wp] = wen ? din : regs[wp];

        dout = ren ? regs[rp] : fOut;
        fOut = ren ? regs[rp] : fOut;

        //read pointer counter
        next_rp = ren ? rp == WIDTH - 1 ? 0 : next_rp + 1 : rp;

        //write pointer counter
        next_wp = wen ? wp == WIDTH - 1 ? 0 : next_wp + 1 : wp;

        valid_read = ren;
    end

endmodule 