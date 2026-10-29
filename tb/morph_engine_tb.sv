module morph_engine_tb;

logic clk;
logic rst_n;
logic prog_we;
logic [3:0] prog_addr;
logic [15:0] prog_data;
logic pin_in;
logic pin_out;
logic sample_reg;
logic [7:0] shift_reg;

morph_engine dut (
    .clk(clk),
    .rst_n(rst_n),
    .prog_we(prog_we),
    .prog_addr(prog_addr),
    .prog_data(prog_data),
    .pin_in(pin_in),
    .pin_out(pin_out),
    .sample_reg(sample_reg),
    .shift_reg(shift_reg)
);

always #5 clk = ~clk;

task load_program(input logic [3:0] addr, input logic [15:0] data);
begin
    @(negedge clk);
    prog_addr = addr;
    prog_data = data;
    prog_we = 1'b1;
    @(negedge clk);
    prog_we = 1'b0;
end
endtask

initial begin
    clk = 0;
    rst_n = 0;
    prog_we = 0;
    prog_addr = 0;
    prog_data = 0;
    pin_in = 0;

    load_program(4'd0, 16'h4001);
    load_program(4'd1, 16'h1001);
    load_program(4'd2, 16'h3004);
    load_program(4'd3, 16'h2000);
    load_program(4'd4, 16'h5000);
    load_program(4'd5, 16'h1000);
    load_program(4'd6, 16'h6000);

    @(negedge clk);
    rst_n = 1;

    repeat(4) @(posedge clk);

    @(negedge clk);
    pin_in = 1;

    repeat(5) @(posedge clk);

    if (pin_out !== 1'b1)
        $fatal(1, "FAIL: DRIVE");

    repeat(8) @(posedge clk);

    if (sample_reg !== 1'b1)
        $fatal(1, "FAIL: SAMPLE");

    #1;

    if (shift_reg[0] !== 1'b1)
        $fatal(1, "FAIL: SHIFT");

    $display("PASS: MORPH programmable engine");

    #20;
    $finish;
end

endmodule
