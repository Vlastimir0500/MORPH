module morph_timer #(
    parameter WIDTH = 8
) (
    input logic clk,
    input logic rst_n,
    input logic enable,
    input logic clear,
    input logic [WIDTH-1:0] period,
    output logic [WIDTH-1:0] count,
    output logic expired
);

always_ff @(posedge clk) begin
    if (!rst_n) begin
        count <= '0;
        expired <= 1'b0;
    end else begin
        expired <= 1'b0;
        if (clear) begin
            count <= '0;
        end else if (enable) begin
            if ((period != 0) && (count == period - 1'b1)) begin
                count <= '0;
                expired <= 1'b1;
            end else begin
                count <= count + 1'b1;
            end
        end
    end
end

endmodule