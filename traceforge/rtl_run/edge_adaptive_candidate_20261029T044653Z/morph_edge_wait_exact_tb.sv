module morph_edge_wait_exact_tb;
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
    integer cycle_count = 0;
    integer periods [0:2];
    integer expected_half;
    integer wait_start;
    integer elapsed;

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

    always #5 clk = ~clk;

    always @(posedge clk)
        cycle_count = cycle_count + 1;

    task automatic write_word(input logic [5:0] address, input logic [15:0] instruction);
        begin
            @(negedge clk);
            program_addr = address;
            program_high_byte = 1'b1;
            program_byte = instruction[15:8];
            @(negedge clk);
            program_high_byte = 1'b0;
            program_byte = instruction[7:0];
            @(negedge clk);
        end
    endtask

    task automatic reset_case;
        begin
            @(negedge clk);
            rst_n = 1'b0;
            pin_in = 8'd0;
            repeat (2) @(negedge clk);
            rst_n = 1'b1;
            repeat (8) @(posedge clk);
            #1;
            if (dut.state != 3'd3) $fatal(1, "EDGE_CAPTURE did not start");
        end
    endtask

    initial begin
        periods[0] = 430;
        periods[1] = 463;
        periods[2] = 407;

        repeat (2) @(negedge clk);
        rst_n = 1'b1;
        program_mode = 1'b1;
        write_word(6'd0, 16'hB002);
        write_word(6'd1, 16'hC000);
        write_word(6'd2, 16'h2000);
        write_word(6'd3, 16'h0000);

        @(negedge clk);
        program_mode = 1'b0;
        rst_n = 1'b0;
        repeat (2) @(negedge clk);
        rst_n = 1'b1;

        for (int j = 0; j < 3; j++) begin
            reset_case();

            @(negedge clk);
            pin_in[0] = 1'b1;
            @(posedge clk);
            #1;

            for (int i = 1; i <= periods[j]; i++) begin
                @(negedge clk);
                if (i == periods[j]) pin_in[0] = 1'b0;
            end

            @(posedge clk);
            #1;

            if (!dut.edge_capture_valid)
                $fatal(1, "Capture validity missing for period %0d", periods[j]);

            if (dut.edge_interval != periods[j])
                $fatal(1, "Interval mismatch: expected %0d got %0d", periods[j], dut.edge_interval);

            wait (dut.state == 3'd5);
            wait_start = cycle_count;
            expected_half = periods[j] / 2;

            if (dut.captured_wait_count != expected_half)
                $fatal(1, "Initial wait count mismatch: expected %0d got %0d", expected_half, dut.captured_wait_count);

            wait (dut.state != 3'd5);
            elapsed = cycle_count - wait_start;

            if (elapsed != expected_half)
                $fatal(1, "Wait duration mismatch: expected %0d cycles got %0d", expected_half, elapsed);

            if (fault)
                $fatal(1, "Unexpected fault at period %0d", periods[j]);

            $display("RTL PASS: interval=%0d, half_wait=%0d, elapsed=%0d", periods[j], expected_half, elapsed);
        end

        $display("EXACT-CYCLE RTL TEST PASS");
        $finish;
    end
endmodule
