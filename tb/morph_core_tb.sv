`timescale 1ns/1ps

module morph_core_tb;

logic clk = 0;
logic rst_n = 0;
logic pin_in = 0;
logic pin_out;

morph_core dut (
    .clk(clk),
    .rst_n(rst_n),
    .pin_in(pin_in),
    .pin_out(pin_out)
);

always #5 clk = ~clk;

initial begin
    $dumpfile("morph_core.vcd");
    $dumpvars(0, morph_core_tb);

    #20 rst_n = 1;
    #20 pin_in = 1;
    #20 pin_in = 0;
    #20 pin_in = 1;
    #40 $finish;
end

endmodule
