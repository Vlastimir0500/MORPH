module morph_isa_decode_tb;

logic [15:0] instr;
logic drive_en;
logic sample_en;
logic wait_en;
logic edge_en;
logic shift_en;
logic branch_en;
logic loop_en;
logic compare_en;
logic trigger_en;
logic expect_en;
logic [3:0] pin_sel;
logic [7:0] arg;

morph_isa_decode dut (
    .instr(instr),
    .drive_en(drive_en),
    .sample_en(sample_en),
    .wait_en(wait_en),
    .edge_en(edge_en),
    .shift_en(shift_en),
    .branch_en(branch_en),
    .loop_en(loop_en),
    .compare_en(compare_en),
    .trigger_en(trigger_en),
    .expect_en(expect_en),
    .pin_sel(pin_sel),
    .arg(arg)
);

task automatic check(
    input logic [15:0] code,
    input logic expected_drive,
    input logic expected_sample,
    input logic expected_wait,
    input logic expected_edge,
    input logic expected_shift,
    input logic expected_branch
);
begin
    instr = code;
    #1;

    if (drive_en !== expected_drive)
        $fatal(1, "DRIVE decode failed");

    if (sample_en !== expected_sample)
        $fatal(1, "SAMPLE decode failed");

    if (wait_en !== expected_wait)
        $fatal(1, "WAIT decode failed");

    if (edge_en !== expected_edge)
        $fatal(1, "EDGE decode failed");

    if (shift_en !== expected_shift)
        $fatal(1, "SHIFT decode failed");

    if (branch_en !== expected_branch)
        $fatal(1, "BRANCH decode failed");

    if (pin_sel !== code[11:8])
        $fatal(1, "PIN decode failed");

    if (arg !== code[7:0])
        $fatal(1, "ARG decode failed");
end
endtask

initial begin
    instr = 16'h0000;

    check(16'h1A55, 1, 0, 0, 0, 0, 0);
    check(16'h2B66, 0, 1, 0, 0, 0, 0);
    check(16'h3C77, 0, 0, 1, 0, 0, 0);
    check(16'h4D88, 0, 0, 0, 1, 0, 0);
    check(16'h5E99, 0, 0, 0, 0, 1, 0);
    check(16'h6FAA, 0, 0, 0, 0, 0, 1);

    instr = 16'hA123;
    #1;

    if (expect_en !== 1'b1)
        $fatal(1, "EXPECT decode failed");

    if (pin_sel !== 4'h1)
        $fatal(1, "EXPECT pin decode failed");

    if (arg !== 8'h23)
        $fatal(1, "EXPECT argument decode failed");

    $display("PASS: MORPH ISA decoder");

    $finish;
end

endmodule
