module morph_reactor_tb;

logic clk;
logic rst_n;
logic pin_in;
logic pin_out;
logic event_seen;

morph_reactor dut (
    .clk(clk),
    .rst_n(rst_n),
    .pin_in(pin_in),
    .pin_out(pin_out),
    .event_seen(event_seen)
);

always #5 clk = ~clk;

initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    pin_in = 1'b0;

    #20;
    rst_n = 1'b1;

    #10;
    pin_in = 1'b1;

    #10;
    pin_in = 1'b0;

    #60;

    if (pin_out !== 1'b1)
        $fatal(1, "FAIL: output did not toggle");

    $display("PASS: event-reactive state machine toggled output");

    #10;
    $finish;
end

endmodule