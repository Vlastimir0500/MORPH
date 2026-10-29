module morph_edge_sample_latency_tb;
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
    integer periods [0:2];
    integer capture_cycle = -1;
    integer sample_cycle = -1;
    integer latency;
    integer half_period;

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
        if (rst_n && !program_mode) begin
            if (capture_cycle < 0 &&
                dut.state == 3'd3 &&
                dut.ir[15:12] == 4'hB &&
                dut.edge_seen &&
                dut.pin_prev[0] != pin_in[0])
                capture_cycle = dut.cycle_counter;

            if (sample_cycle < 0 &&
                dut.state == 3'd1 &&
                dut.ir == 16'h2000)
                sample_cycle = dut.cycle_counter;
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
            pin_in = 8'd1;
            rst_n = 1'b0;
            repeat (2) @(negedge clk);
            rst_n = 1'b1;
            repeat (8) @(posedge clk);
            #1;
            if (dut.state != 3'd3)
                $fatal(1, "EDGE_CAPTURE did not start");
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
            pin_in[0] = 1'b0;

            @(posedge clk);
            #1;
            if (!dut.edge_seen)
                $fatal(1, "First edge was not registered");

            for (int i = 1; i <= periods[j]; i++) begin
                @(negedge clk);
                if (i == periods[j])
                    pin_in[0] = 1'b1;
            end

            wait (sample_cycle >= 0);
            #1;

            if (dut.edge_interval != periods[j])
                $fatal(1, "Expected interval %0d, got %0d", periods[j], dut.edge_interval);

            if (!dut.edge_capture_valid)
                $fatal(1, "Capture validity missing");

            if (sample_reg !== 1'b1)
                $fatal(1, "Sample did not read the high input");

            latency = sample_cycle - capture_cycle;
            half_period = periods[j] / 2;

            if (latency < half_period || latency > half_period + 8)
                $fatal(1, "Unexpected sample latency: period=%0d latency=%0d", periods[j], latency);

            if (fault)
                $fatal(1, "Unexpected fault");

            $display("RTL PASS: period=%0d half=%0d edge_to_sample=%0d offset=%0d",
                periods[j], half_period, latency, latency - half_period);
        end

        $display("EDGE SAMPLE LATENCY TEST PASS");
        $finish;
    end
endmodule
