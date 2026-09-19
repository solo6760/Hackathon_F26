module PE #(
    
) (
    input logic clk,
    input logic n_rst,
    input logic signed [7:0] int8,
    input logic signed [3:0] int4,
    input logic signed [31:0] prevSum,
    input logic validInput,
    output logic signed [31:0] out,
    output logic signed [7:0] rightPass,
    output logic signed [3:0] downPass
);

    logic signed [31:0] sum, next_sum;
    logic signed [7:0] int8reg, next8;
    logic signed [3:0] int4reg, next4;

    always_ff @(posedge clk, negedge n_rst) begin
        if(!n_rst) begin
            sum <= {32{1'b0}};
            int8reg <= {8{1'b0}};
            int4reg <= {4{1'b0}};
        end
        else if(validInput) begin
            sum <= next_sum;
            int8reg <= next8;
            int4reg <= next4;
        end
    end

    always_comb begin
        next8 = int8;
        next4 = int4;

        next_sum = (int8reg * int4reg) + prevSum;
        out = sum;

        rightPass = int8reg;
        downPass = int4reg;
    end

endmodule