
module morph_uart_55_calibration_tb;
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

    integer cycle_count = 0;
    integer transition_count = 0;
    integer first_edge_cycle = -1;
    integer capture_cycle = -1;
    integer sample_cycle = -1;
    integer actual_offset;
    integer i;
    integer transition_cycles [0:9];

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
            if (dut.pin_prev[0] != pin_in[0]) begin
                if (transition_count < 10)
                    transition_cycles[transition_count] = cycle_count;
                transition_count = transition_count + 1;
            end

            if (first_edge_cycle < 0 &&
                dut.state == 3'd3 &&
                dut.ir[15:12] == 4'hB &&
                !dut.edge_seen &&
                dut.pin_prev[0] != pin_in[0])
                first_edge_cycle = cycle_count;

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

    task automatic write_word(
        input logic [5:0] address,
        input logic [15:0] instruction
    );
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

    initial begin
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

        repeat (8) @(posedge clk);
        #1;

        if (dut.state != 3'd3)
            $fatal(1, "EDGE_CAPTURE did not start");

        @(negedge clk);
        pin_in[0] = 1'b0;

        @(posedge clk);
        #1;

        if (!dut.edge_seen)
            $fatal(1, "UART start edge was not detected");

        for (int bit_index = 0; bit_index < 8; bit_index++) begin
            repeat (40) @(negedge clk);
            pin_in[0] = (bit_index % 2 == 0) ? 1'b1 : 1'b0;
        end

        repeat (40) @(negedge clk);
        pin_in[0] = 1'b1;

        repeat (2) @(posedge clk);
        #1;

        if (transition_count != 10)
            $fatal(1, "Expected 10 transitions, observed %0d", transition_count);

        for (i = 1; i < 10; i++) begin
            if (transition_cycles[i] - transition_cycles[i-1] != 40)
                $fatal(1, "Transition gap %0d was %0d clocks",
                       i, transition_cycles[i] - transition_cycles[i-1]);
        end

        if (first_edge_cycle < 0 || capture_cycle < 0 || sample_cycle < 0)
            $fatal(1, "Missing edge or sample event");

        if (!dut.edge_capture_valid || dut.edge_interval != 40)
            $fatal(1, "Expected captured bit period 40, got %0d",
                   dut.edge_interval);

        actual_offset = sample_cycle - capture_cycle;

        if (actual_offset != 20)
            $fatal(1, "Expected first data-bit center at +20, got +%0d",
                   actual_offset);

        if (sample_reg !== 1'b1)
            $fatal(1, "Expected high sample for first bit of 0x55");

        if (fault)
            $fatal(1, "Unexpected RTL fault");

        $display("UART PATTERN: start + 0x55 data + stop");
        $display("BIT PERIOD: 40 clocks");
        $display("TRANSITIONS: %0d, every 40 clocks", transition_count);
        $display("CAPTURED INTERVAL: %0d clocks", dut.edge_interval);
        $display("FIRST DATA SAMPLE: offset=%0d, expected=20, value=%0b",
                 actual_offset, sample_reg);
        $display("UART 0x55 CALIBRATION TEST PASS");
        $finish;
    end
endmodule
