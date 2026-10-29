module morph_all_legal_loop_counts(input logic clk);
    (* anyconst *) logic [5:0] loop_count;
    logic [9:0] phase = 10'd0;
    logic reset_seen = 1'b0;

    wire rst_n = phase != 10'd0;
    wire program_mode = phase >= 10'd1 && phase <= 10'd8;
    wire program_high_byte = phase[0];
    wire [5:0] program_addr = (phase - 10'd1) >> 1;
    wire [15:0] selected_word = program_word(program_addr, loop_count);
    wire [7:0] program_byte =
        program_high_byte ? selected_word[15:8] : selected_word[7:0];

    logic [7:0] pin_out;
    logic [7:0] pin_oe;
    logic sample_reg;
    logic [7:0] shift_reg;
    logic timed_out;
    logic fault;

    function automatic [15:0] program_word(
        input [5:0] addr,
        input [5:0] count
    );
        begin
            case (addr)
                6'd0: program_word = 16'h1001;
                6'd1: program_word = 16'h1000;
                6'd2: program_word = {4'h9, count, 6'd0};
                6'd3: program_word = 16'h0000;
                default: program_word = 16'h0000;
            endcase
        end
    endfunction

    morph_engine_v2 dut (
        .clk(clk),
        .rst_n(rst_n),
        .program_mode(program_mode),
        .program_high_byte(program_high_byte),
        .program_addr(program_addr),
        .program_byte(program_byte),
        .pin_in(8'd0),
        .pin_out(pin_out),
        .pin_oe(pin_oe),
        .sample_reg(sample_reg),
        .shift_reg(shift_reg),
        .timed_out(timed_out),
        .fault(fault)
    );

    always_ff @(posedge clk) begin
        assume(loop_count != 6'd0);

        if (!rst_n)
            reset_seen <= 1'b1;

        if (phase < 10'd430)
            phase <= phase + 1'b1;

        if (reset_seen && rst_n)
            assert(!fault);

        if (phase == 10'd11)
            assert(pin_out[0]);

        if (phase == 10'd13)
            assert(!pin_out[0]);

        if (phase == 10'd420) begin
            assert(reset_seen);
            assert(!fault);
            assert(pin_out[0] == 1'b0);
            assert(pin_oe[0] == 1'b1);
        end
    end
endmodule
