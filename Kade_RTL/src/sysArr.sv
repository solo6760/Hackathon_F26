module sysArr #(
    SIZE = 16 //the n x n dimensions of the systolic array
) (
    input logic clk,
    input logic n_rst,
    input logic signed [3:0] vertInput [SIZE-1:0],
    input logic signed [7:0] horizInput [SIZE-1:0],
    input logic load_en,
    input logic acc_clr,
    input logic acc_en,
    input logic shift_en,
    input logic [$clog2(SIZE):0] count,
    output logic signed [31:0] out [SIZE-1:0]
);

    logic [3:0] vertPass [SIZE-1:0][SIZE-2:0];  
    logic [7:0] horizPass [SIZE-1:0][SIZE-2:0];  

    logic signed [31:0] sums [SIZE-1:0][SIZE-1:0];

    //logic validInput [SIZE-1:0];

    //logic [$clog2(SIZE):0] inputCount;

    genvar col, row;

    generate 
        for(col = 0; col < SIZE; col++) begin // column
            for(row = 0; row < SIZE; row++) begin : processUnits //row
                PU inst(
                    .clk(clk),
                    .n_rst(n_rst),
                    .int8(col == 0 ? horizInput[row] : horizPass[row][col-1]),
                    .int4(row == 0 ? vertInput[col] : vertPass[row-1][col]),
                    .prevSum(row == 0 ? {32{1'b0}} : sums[row - 1][col]),
                    //.validInput(validInput[col]),
                    .out(sums[row][col]),
                    .rightPass(horizPass[row][col]),
                    .downPass(vertPass[row][col]),
                    .acc_clr(acc_clr),
                    .acc_en(acc_en),
                    .shift_en(shift_en)
                );
            end
        end
    endgenerate

    
    assign out = sums[count];

endmodule