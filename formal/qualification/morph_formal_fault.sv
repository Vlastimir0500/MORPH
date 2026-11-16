module morph_formal_fault (
    input wire clk,
    input wire rst_n,
    input wire program_mode,
    input wire program_high_byte,
    input wire [5:0] program_addr,
    input wire [7:0] program_byte,
    input wire [7:0] pin_in
);
    wire [7:0] pin_out;
    wire [7:0] pin_oe;
    wire sample_reg;
    wire [7:0] shift_reg;
    wire timed_out;
    wire fault;

    morph_engine_v2 dut (
        .clk(clk),
        .rst_n(rst_n),
        .program_mode(program_mode),
        .program_high_byte(program_high_byte),
        .program_addr(program_addr),
        .program_byte(program_byte),
        .pin_in(pin_in),
        .pin_out(pin_out),
        .pin_oe(pin_oe),
        .sample_reg(sample_reg),
        .shift_reg(shift_reg),
        .timed_out(timed_out),
        .fault(fault)
    );

    reg reset_seen = 1'b0;
    always @(posedge clk)
        reset_seen <= 1'b1;

    always @* begin
        if (!reset_seen)
            assume (!rst_n);
        if (reset_seen && fault)
            assert (pin_oe == 8'h00);
    end
endmodule
