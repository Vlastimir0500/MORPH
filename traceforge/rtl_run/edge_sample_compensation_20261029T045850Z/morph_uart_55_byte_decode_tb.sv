
module morph_uart_55_byte_decode_tb;
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

    logic [15:0] instructions [0:32];
    integer cycle_count = 0;
    integer transition_count = 0;
    integer transition_cycles [0:9];
    integer sample_count = 0;
    integer sample_cycles [0:7];
    logic sampled_bits [0:7];
    integer capture_cycle = -1;
    integer actual_offset;
    integer expected_offset;
    integer timing_error;
    integer j;
    integer p;

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

            if (capture_cycle < 0 &&
                dut.state == 3'd3 &&
                dut.ir[15:12] == 4'hB &&
                dut.edge_seen &&
                dut.pin_prev[0] != pin_in[0])
                capture_cycle = cycle_count;

            if (sample_count < 8 &&
                dut.state == 3'd1 &&
                dut.ir == 16'h2000) begin
                sample_cycles[sample_count] = cycle_count;
                sampled_bits[sample_count] = pin_in[0];
                sample_count = sample_count + 1;
            end
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
        p = 0;
        instructions[p] = 16'hB002;
        p = p + 1;
        instructions[p] = 16'hC000;
        p = p + 1;
        instructions[p] = 16'h2000;
        p = p + 1;
        instructions[p] = 16'h5000;
        p = p + 1;

        for (j = 1; j < 8; j = j + 1) begin
            instructions[p] = 16'hC000;
            p = p + 1;
            instructions[p] = 16'hC000;
            p = p + 1;
            instructions[p] = 16'h2000;
            p = p + 1;
            instructions[p] = 16'h5000;
            p = p + 1;
        end

        instructions[p] = 16'h0000;

        repeat (2) @(negedge clk);
        rst_n = 1'b1;
        program_mode = 1'b1;

        for (j = 0; j <= p; j = j + 1)
            write_word(j[5:0], instructions[j]);

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
            $fatal(1, "Start edge was not detected");

        for (j = 0; j < 8; j = j + 1) begin
            repeat (40) @(negedge clk);
            pin_in[0] = (j % 2 == 0) ? 1'b1 : 1'b0;
        end

        repeat (40) @(negedge clk);
        pin_in[0] = 1'b1;

        repeat (100) @(posedge clk);
        #1;

        if (transition_count != 10)
            $fatal(1, "Expected 10 UART transitions, got %0d",
                   transition_count);

        for (j = 1; j < 10; j = j + 1) begin
            if (transition_cycles[j] - transition_cycles[j-1] != 40)
                $fatal(1, "Transition gap %0d was %0d clocks",
                       j, transition_cycles[j] - transition_cycles[j-1]);
        end

        if (sample_count != 8)
            $fatal(1, "Expected 8 samples, got %0d", sample_count);

        if (capture_cycle < 0)
            $fatal(1, "Missing edge capture event");

        if (!dut.edge_capture_valid || dut.edge_interval != 40)
            $fatal(1, "Expected captured period 40, got %0d",
                   dut.edge_interval);

        for (j = 0; j < 8; j = j + 1) begin
            expected_offset = 20 + 40*j;
            actual_offset = sample_cycles[j] - capture_cycle;
            timing_error = actual_offset - expected_offset;

            if (timing_error > 8 || timing_error < -8)
                $fatal(1, "Sample %0d timing error %0d cycles",
                       j, timing_error);

            if (sampled_bits[j] !== ((j % 2) == 0))
                $fatal(1, "Sample %0d wrong: got %0b",
                       j, sampled_bits[j]);

            $display("BIT %0d: value=%0b offset=%0d ideal=%0d error=%0d",
                     j, sampled_bits[j], actual_offset,
                     expected_offset, timing_error);
        end

        if (shift_reg !== 8'hAA)
            $fatal(1, "Expected shift_reg=0xAA, got 0x%02x", shift_reg);

        if (fault)
            $fatal(1, "Unexpected RTL fault");

        $display("UART BYTE DECODE PASS: input=0x55 shift_reg=0x%02x",
                 shift_reg);
        $finish;
    end
endmodule
