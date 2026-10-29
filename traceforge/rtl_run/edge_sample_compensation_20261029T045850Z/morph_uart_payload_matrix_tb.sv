
module morph_uart_payload_matrix_tb;
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
    logic [7:0] payloads [0:5];
    integer cycle_count = 0;
    integer transition_count = 0;
    integer sample_count = 0;
    integer transition_cycles [0:9];
    integer sample_cycles [0:7];
    logic sampled_bits [0:7];
    integer capture_cycle = -1;
    integer case_failures;
    integer total_failures = 0;
    integer case_index;
    integer bit_index;
    integer instruction_index;
    integer j;
    integer k;
    integer expected_offset;
    integer actual_offset;
    integer timing_error;

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

    task automatic run_case(input logic [7:0] payload);
        begin
            @(negedge clk);
            rst_n = 1'b0;
            pin_in = 8'd1;
            transition_count = 0;
            sample_count = 0;
            capture_cycle = -1;

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

            for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin
                repeat (40) @(negedge clk);
                pin_in[0] = payload[bit_index];
            end

            repeat (40) @(negedge clk);
            pin_in[0] = 1'b1;

            repeat (5000) @(posedge clk);
            #1;

            case_failures = 0;

            if (dut.edge_interval != 40) begin
                $display("CAPTURE GAP MISMATCH: got=%0d expected=40",
                         dut.edge_interval);
                case_failures = case_failures + 1;
            end

            if (sample_count != 8) begin
                $display("SAMPLE COUNT MISMATCH: got=%0d expected=8",
                         sample_count);
                case_failures = case_failures + 1;
            end

            if (capture_cycle < 0) begin
                $display("EDGE CAPTURE EVENT MISSING");
                case_failures = case_failures + 1;
            end

            for (k = 0; k < 8; k = k + 1) begin
                if (sample_count > k) begin
                    expected_offset = 20 + 40*k;
                    actual_offset = sample_cycles[k] - capture_cycle;
                    timing_error = actual_offset - expected_offset;

                    $display("BIT %0d: got=%0b expected=%0b offset=%0d ideal=%0d error=%0d",
                             k, sampled_bits[k], payload[k],
                             actual_offset, expected_offset, timing_error);

                    if (sampled_bits[k] !== payload[k])
                        case_failures = case_failures + 1;

                    if (timing_error > 8 || timing_error < -8)
                        case_failures = case_failures + 1;
                end
            end

            $display("PAYLOAD 0x%02x: captured_period=%0d shift_reg=0x%02x faults=%0d",
                     payload, dut.edge_interval, shift_reg, fault);

            if (fault || shift_reg !== reverse_byte(payload))
                case_failures = case_failures + 1;

            if (case_failures == 0)
                $display("CASE PASS: payload=0x%02x", payload);
            else begin
                $display("CASE LIMITATION EXPOSED: payload=0x%02x errors=%0d",
                         payload, case_failures);
                total_failures = total_failures + 1;
            end
        end
    endtask

    function automatic [7:0] reverse_byte(input logic [7:0] value);
        integer r;
        begin
            reverse_byte = 8'd0;
            for (r = 0; r < 8; r = r + 1)
                reverse_byte[7-r] = value[r];
        end
    endfunction

    initial begin
        instructions[0] = 16'hB002;
        instructions[1] = 16'hC000;
        instructions[2] = 16'h2000;
        instructions[3] = 16'h5000;

        instruction_index = 4;

        for (j = 1; j < 8; j = j + 1) begin
            instructions[instruction_index] = 16'hC000;
            instruction_index = instruction_index + 1;
            instructions[instruction_index] = 16'hC000;
            instruction_index = instruction_index + 1;
            instructions[instruction_index] = 16'h2000;
            instruction_index = instruction_index + 1;
            instructions[instruction_index] = 16'h5000;
            instruction_index = instruction_index + 1;
        end

        instructions[32] = 16'h0000;

        payloads[0] = 8'h55;
        payloads[1] = 8'hFF;
        payloads[2] = 8'h00;
        payloads[3] = 8'hA6;
        payloads[4] = 8'hC3;
        payloads[5] = 8'h01;

        repeat (2) @(negedge clk);
        rst_n = 1'b1;
        program_mode = 1'b1;

        for (j = 0; j <= 32; j = j + 1)
            write_word(j[5:0], instructions[j]);

        @(negedge clk);
        program_mode = 1'b0;
        rst_n = 1'b0;

        for (case_index = 0; case_index < 6; case_index = case_index + 1) begin
            $display("\n===== TEST PAYLOAD 0x%02x =====", payloads[case_index]);
            run_case(payloads[case_index]);
        end

        $display("\nPAYLOAD MATRIX COMPLETE: 6 cases, %0d cases with failures",
                 total_failures);
        $finish;
    end
endmodule
