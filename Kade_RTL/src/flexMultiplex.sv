module flexMultiplex #(
    IN_SIZE = 16,
    ELEMENT_SIZE = 8
) (
    input logic signed [ELEMENT_SIZE-1:0] data [IN_SIZE-1:0],
    input logic [$clog2(IN_SIZE - 1):0] sel,
    input logic en,
    
    
    output logic signed [ELEMENT_SIZE-1:0] out
);

    always_comb begin
        out = en ? data[sel] : '0;
    end

endmodule