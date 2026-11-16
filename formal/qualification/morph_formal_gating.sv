module morph_formal_gating (
    input wire [7:0] ui_in,
    input wire [7:0] uio_in,
    input wire ena,
    input wire clk,
    input wire rst_n
);
    wire [7:0] uo_out;
    wire [7:0] uio_out;
    wire [7:0] uio_oe;

    tt_um_rattandeep_morph_v2 dut (
        .ui_in(ui_in),
        .uo_out(uo_out),
        .uio_in(uio_in),
        .uio_out(uio_out),
        .uio_oe(uio_oe),
        .ena(ena),
        .clk(clk),
        .rst_n(rst_n)
    );

    always @* begin
        if (!ena)
            assert (uio_oe == 8'h00);
        if (!rst_n)
            assert (uio_oe == 8'h00);
        if (ui_in[7])
            assert (uio_oe == 8'h00);
    end
endmodule
