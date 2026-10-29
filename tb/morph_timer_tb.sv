module morph_timer_tb;

logic clk;
logic rst_n;
logic enable;
logic clear;
logic [7:0] period;
logic [7:0] count;
logic expired;

morph_timer dut (
    .clk(clk),
    .rst_n(rst_n),
    .enable(enable),
    .clear(clear),
    .period(period),
    .count(count),
    .expired(expired)
);

always #5 clk = ~clk;

always @(posedge clk)
    $display("time=%0t count=%0d expired=%b", $time, count, expired);

initial begin
    clk = 0;
    rst_n = 0;
    enable = 0;
    clear = 0;
    period = 8;

    #20 rst_n = 1;
    enable = 1;

    #100 clear = 1;
    #10 clear = 0;
    #50 $finish;
end

endmodule