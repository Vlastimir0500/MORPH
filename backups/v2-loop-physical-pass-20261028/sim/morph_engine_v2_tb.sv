module morph_engine_v2_tb;

    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic program_mode = 1'b0;
    logic program_high_byte = 1'b0;
    logic [5:0] program_addr = 6'd0;
    logic [7:0] program_byte = 8'd0;
    logic [7:0] pin_in = 8'd0;
    logic [7:0] pin_out;
    logic [7:0] pin_oe;
    logic sample_reg;
    logic [7:0] shift_reg;
    logic timed_out;
    logic fault;

    always #5 clk = ~clk;

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

    task automatic pulse;
        begin
            @(posedge clk);
            #1;
        end
    endtask

    task automatic write_word(input logic [5:0] address, input logic [15:0] word);
        begin
            program_mode = 1'b1;
            program_addr = address;
            program_high_byte = 1'b0;
            program_byte = word[7:0];
            pulse();
            program_high_byte = 1'b1;
            program_byte = word[15:8];
            pulse();
        end
    endtask

    task automatic start_run;
        begin
            program_mode = 1'b0;
            rst_n = 1'b0;
            repeat (2) pulse();
            rst_n = 1'b1;
            pulse();
        end
    endtask

    initial begin
        pin_in = 8'd0;
        pulse();
        write_word(6'd0, 16'h1301);
        write_word(6'd1, 16'h7300);
        start_run();
        repeat (10) pulse();
        if (pin_oe[3] !== 1'b0 || pin_oe[2:0] !== 3'b000)
            $fatal(1, "Per-pin drive/release test failed");
        if (fault !== 1'b0)
            $fatal(1, "Unexpected fault in drive/release test");
        $display("PASS: per-pin drive and release");

        pin_in = 8'h20;
        write_word(6'd0, 16'h2500);
        write_word(6'd1, 16'h5000);
        write_word(6'd2, 16'h0000);
        start_run();
        repeat (10) pulse();
        if (sample_reg !== 1'b1 || shift_reg !== 8'h01)
            $fatal(1, "Sample/shift test failed");
        if (fault !== 1'b0)
            $fatal(1, "Unexpected fault in sample/shift test");
        $display("PASS: selected-pin sampling and shift register");

        pin_in = 8'h00;
        write_word(6'd0, 16'h4207);
        write_word(6'd1, 16'h1401);
        write_word(6'd2, 16'h0000);
        start_run();
        repeat (12) pulse();
        if (timed_out !== 1'b1 || fault !== 1'b1 || pin_oe !== 8'h00)
            $fatal(1, "Bounded edge timeout test failed");
        if (pin_oe[4] !== 1'b0)
            $fatal(1, "Instruction after timeout executed");
        $display("PASS: bounded edge timeout halts and releases pins");

        pin_in = 8'h20;
        write_word(6'd0, 16'h2500);
        write_word(6'd1, 16'h8083);
        write_word(6'd2, 16'h1101);
        write_word(6'd3, 16'h1201);
        write_word(6'd4, 16'h0000);
        start_run();
        repeat (12) pulse();
        if (pin_oe[2] !== 1'b1 || pin_out[2] !== 1'b1)
            $fatal(1, "Conditional branch target did not execute");
        if (pin_oe[1] !== 1'b0)
            $fatal(1, "Conditional branch failed to skip instruction");
        if (fault !== 1'b0)
            $fatal(1, "Unexpected fault in conditional branch test");
        $display("PASS: sample-conditioned branch");

        $display("ALL MORPH V2 TESTS PASSED");
        $finish;
    end

endmodule
