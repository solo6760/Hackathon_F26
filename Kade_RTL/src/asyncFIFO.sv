module asyncFIFO #(
    parameter int I_SIZE = 8,
    parameter int O_SIZE = 8,
    parameter int WIDTH  = 4
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

    localparam int PTR_W = $clog2(WIDTH);
    logic [I_SIZE-1:0] regs [WIDTH-1:0];
    logic [PTR_W:0] rp, wp;

    always_ff @(posedge clk, negedge n_rst) begin
        if (!n_rst) begin
            regs       <= '{default: '0};
            rp         <= '0;
            wp         <= '0;
            dout       <= '0;
            valid_read <= 1'b0;
        end else begin
            if (wen && !full) begin
                regs[wp[PTR_W-1:0]] <= din;
                wp <= wp + 1'b1;
            end
            if (ren && !empty) begin
                dout <= regs[rp[PTR_W-1:0]];
                rp   <= rp + 1'b1;
                valid_read <= 1'b1;
            end else begin
                valid_read <= 1'b0;
            end
        end
    end

    always_comb begin
        empty = (rp == wp);
        full  = (rp[PTR_W] != wp[PTR_W]) && (rp[PTR_W-1:0] == wp[PTR_W-1:0]);
    end

endmodule
