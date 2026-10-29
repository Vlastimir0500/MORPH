module morph_edge_sample_compensation_tb;
    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic program_mode = 1'b0;
    logic program_high_byte = 1'b0;
    logic [5:0] program_addr = 6'd0;
    logic [7:0] program_byte = 8'd0;
    logic [7:0] pin_in = 8'd1;
    logic [7:0] pin_out;
    logic [7:0] pin_oe;
    logic sample_reg;
    logic [7:0] shift_reg;
    logic timed_out;
    logic fault;
    logic [15:0] periods [0:13];
    integer cycle_count = 0;
    integer capture_cycle = -1;
    integer sample_cycle = -1;
    integer expected_half;
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

    always @(posedge clk) begin
        cycle_count = cycle_count + 1;
        if (rst_n && !program_mode) begin
            if (capture_cycle < 0 &&
                dut.state == 3'd3 &&
                dut.ir[15:12] == 4'hB &&
                dut.edge_seen &&
                dut.pin_prev[0] != pin_in[0])
                capture_cycle = cycle_count;

            if (sample_cycle < 0 &&
                dut.state == 3'd1 &&
                dut.ir == 16'h2000)
                sample_cycle = cycle_count;
        end
    end

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
            capture_cycle = -1;
            sample_cycle = -1;
            @(negedge clk);
            rst_n = 1'b0;
            pin_in = 8'd1;
            repeat (2) @(negedge clk);
            rst_n = 1'b1;
            repeat (8) @(posedge clk);
            #1;
            if (dut.state != 3'd3)
                $fatal(1, "EDGE_CAPTURE did not start");
        end
    endtask

    initial begin
        periods[0] = 16'd10;
        periods[1] = 16'd11;
        periods[2] = 16'd20;
        periods[3] = 16'd37;
        periods[4] = 16'd101;
        periods[5] = 16'd255;
        periods[6] = 16'd350;
        periods[7] = 16'd403;
        periods[8] = 16'd407;
        periods[9] = 16'd430;
        periods[10] = 16'd463;
        periods[11] = 16'd479;
        periods[12] = 16'd520;
        periods[13] = 16'd1023;

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

        for (int j = 0; j < 14; j++) begin
            reset_case();

            @(negedge clk);
            pin_in[0] = 1'b0;
            @(posedge clk);
            #1;

            if (!dut.edge_seen)
                $fatal(1, "First transition was not captured");

            for (int i = 1; i <= periods[j]; i++) begin
                @(negedge clk);
                if (i == periods[j])
                    pin_in[0] = 1'b1;
            end

            wait (sample_cycle >= 0);
            #1;

            if (capture_cycle < 0)
                $fatal(1, "Capture cycle was not recorded");

            if (!dut.edge_capture_valid)
                $fatal(1, "Capture validity missing");

            if (dut.edge_interval != periods[j])
                $fatal(1, "Period %0d: captured %0d", periods[j], dut.edge_interval);

            expected_half = periods[j] / 2;
            elapsed = sample_cycle - capture_cycle;

            if (elapsed != expected_half)
                $fatal(1, "Period %0d: expected sample offset %0d, got %0d", periods[j], expected_half, elapsed);

            if (sample_reg !== 1'b1)
                $fatal(1, "Period %0d: expected high sample", periods[j]);

            if (fault)
                $fatal(1, "Unexpected fault for period %0d", periods[j]);

            $display("RTL PASS: period=%0d target=%0d actual=%0d", periods[j], expected_half, elapsed);
        end

        $display("SAMPLE COMPENSATION RTL TEST PASS: 14/14");
        $finish;
    end
endmodule
