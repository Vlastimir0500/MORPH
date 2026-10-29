module morph_edge_adaptive_tb;
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
    logic [15:0] expected_period;
    integer periods [0:2];

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

    task automatic reset_engine;
        begin
            @(negedge clk);
            rst_n = 1'b0;
            pin_in = 8'd0;
            repeat (2) @(negedge clk);
            rst_n = 1'b1;
            repeat (8) @(posedge clk);
            #1;
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
            expected_period = periods[j];
            reset_engine();

            @(negedge clk);
            pin_in[0] = 1'b1;
            @(posedge clk);
            #1;

            if (!dut.edge_seen) $fatal(1, "Initial edge not captured");
            if (dut.edge_capture_valid) $fatal(1, "Interval became valid after one edge");
            if (dut.state != 3'd3) $fatal(1, "Capture did not wait for the second edge");

            for (int i = 1; i <= periods[j]; i++) begin
                @(negedge clk);
                if (i == periods[j]) pin_in[0] = 1'b0;
            end

            @(posedge clk);
            #1;

            if (!dut.edge_capture_valid) $fatal(1, "Capture validity not asserted");
            if (dut.edge_interval != expected_period)
                $fatal(1, "Expected interval %0d, got %0d", expected_period, dut.edge_interval);

            repeat (2) @(posedge clk);
            #1;

            if (dut.state != 3'd5) $fatal(1, "Dynamic half-period wait did not start");
            if (dut.captured_wait_count != (expected_period >> 1))
                $fatal(1, "Expected half-period %0d, got %0d", expected_period >> 1, dut.captured_wait_count);

            repeat ((periods[j] / 2) + 10) @(posedge clk);
            #1;

            if (sample_reg !== 1'b0) $fatal(1, "Sample was not taken at the low level");
            if (fault) $fatal(1, "Unexpected RTL fault");

            $display("RTL PASS: edge interval %0d, half wait %0d", expected_period, expected_period >> 1);
        end

        $display("EDGE ADAPTIVE RTL TEST PASS");
        $finish;
    end
endmodule
