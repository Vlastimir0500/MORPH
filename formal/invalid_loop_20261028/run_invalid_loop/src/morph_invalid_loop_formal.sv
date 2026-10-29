module morph_invalid_loop_formal(input logic clk);
    (* anyconst *) logic [5:0] bad_count;
    (* anyconst *) logic [5:0] bad_target;

    logic [3:0] phase = 4'd0;
    logic reset_seen = 1'b0;
    logic fault_seen = 1'b0;

    wire rst_n = (phase != 4'd0);
    wire program_mode = (phase >= 4'd1) && (phase <= 4'd4);
    wire program_high_byte = (phase == 4'd1) || (phase == 4'd3);
    wire [5:0] program_addr = (phase <= 4'd2) ? 6'd0 : 6'd1;
    wire [15:0] bad_loop_word = {4'h9, bad_count, bad_target};

    wire [7:0] program_byte =
        (phase == 4'd1) ? 8'h11 :
        (phase == 4'd2) ? 8'h01 :
        (phase == 4'd3) ? bad_loop_word[15:8] :
        (phase == 4'd4) ? bad_loop_word[7:0] :
        8'h00;

    logic [7:0] pin_out;
    logic [7:0] pin_oe;
    logic sample_reg;
    logic [7:0] shift_reg;
    logic timed_out;
    logic fault;

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

    always_comb begin
        assume((bad_count == 6'd0) || (bad_target >= 6'd1));
    end

    always_ff @(posedge clk) begin
        if (!rst_n)
            reset_seen <= 1'b1;

        if (phase < 4'd15)
            phase <= phase + 1'b1;

        if (reset_seen && rst_n && fault) begin
            assert(pin_oe == 8'd0);
            fault_seen <= 1'b1;
        end

        if (fault_seen) begin
            assert(fault);
            assert(pin_oe == 8'd0);
        end

        if (phase == 4'd11) begin
            assert(reset_seen);
            assert(fault_seen);
            assert(fault);
            assert(pin_oe == 8'd0);
        end
    end
endmodule
