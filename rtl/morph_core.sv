module morph_core (
    input  logic clk,
    input  logic rst_n,

    input  logic pin_in,
    output logic pin_out
);

    logic pin_prev;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            pin_prev <= 1'b0;
        end else begin
            pin_prev <= pin_in;
        end
    end

    always_comb begin
        pin_out = pin_in ^ pin_prev;
    end

endmodule
