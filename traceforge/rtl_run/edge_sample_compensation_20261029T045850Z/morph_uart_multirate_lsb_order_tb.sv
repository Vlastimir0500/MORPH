
module morph_uart_multirate_lsb_order_tb;
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

    logic [15:0] instructions [0:47];
    logic [7:0] payloads [0:5];
    integer periods [0:3];
    integer active_period = 40;
    integer cycle_count = 0;
    integer sample_count = 0;
    integer sample_cycles [0:9];
    logic sampled_bits [0:9];
    integer capture_cycle = -1;
    integer edge_wait_count = 0;
    integer payload_start_cycle = -1;
    integer total_failures = 0;
    integer case_failures;
    integer p;
    integer j;
    integer edge_index;
    integer bit_index;
    integer period_index;
    integer actual_offset;
    integer expected_offset;
    integer timing_error;
    integer abs_error;
    integer max_error;
    integer expected_bit;

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

            if (dut.state == 3'd3 &&
                dut.ir[15:12] == 4'h4 &&
                ((dut.ir[0] && pin_in[0] && !dut.pin_prev[0]) ||
                 (!dut.ir[0] && !pin_in[0] && dut.pin_prev[0]))) begin
                edge_wait_count = edge_wait_count + 1;
                if (edge_wait_count == 9)
                    payload_start_cycle = cycle_count;
            end

            if (sample_count < 10 &&
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

    task automatic send_uart_byte(input logic [7:0] data);
        integer b;
        begin
            @(negedge clk);
            pin_in[0] = 1'b0;
            repeat (active_period) @(negedge clk);

            for (b = 0; b < 8; b = b + 1) begin
                pin_in[0] = data[b];
                repeat (active_period) @(negedge clk);
            end

            pin_in[0] = 1'b1;
            repeat (active_period) @(negedge clk);
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

    task automatic run_case(
        input logic [7:0] payload,
        input integer bit_period
    );
        integer b;
        begin
            active_period = bit_period;
            @(negedge clk);
            rst_n = 1'b0;
            pin_in = 8'd1;
            sample_count = 0;
            capture_cycle = -1;
            edge_wait_count = 0;
            payload_start_cycle = -1;

            repeat (2) @(negedge clk);
            rst_n = 1'b1;
            repeat (8) @(posedge clk);
            #1;

            if (dut.state != 3'd3)
                $fatal(1, "EDGE_CAPTURE did not start");

            send_uart_byte(8'h55);
            send_uart_byte(payload);

            repeat (100) @(posedge clk);
            #1;

            case_failures = 0;
            max_error = 0;

            if (sample_count != 10) begin
                $display("SAMPLE COUNT ERROR: period=%0d payload=0x%02x count=%0d",
                         bit_period, payload, sample_count);
                case_failures = case_failures + 1;
            end

            if (!dut.edge_capture_valid ||
                dut.edge_interval != bit_period) begin
                $display("CAPTURE ERROR: period=%0d payload=0x%02x captured=%0d valid=%0b",
                         bit_period, payload, dut.edge_interval,
                         dut.edge_capture_valid);
                case_failures = case_failures + 1;
            end

            if (capture_cycle < 0 || payload_start_cycle < 0) begin
                $display("MISSING EDGE EVENT: period=%0d payload=0x%02x",
                         bit_period, payload);
                case_failures = case_failures + 1;
            end

            if (sample_count > 0 && capture_cycle >= 0) begin
                actual_offset = sample_cycles[0] - capture_cycle;
                expected_offset = bit_period / 2;
                timing_error = actual_offset - expected_offset;

                if (sampled_bits[0] !== 1'b1 ||
                    timing_error < -2 || timing_error > 2) begin
                    $display("TRAINING SAMPLE ERROR: period=%0d value=%0b offset=%0d expected=%0d",
                             bit_period, sampled_bits[0],
                             actual_offset, expected_offset);
                    case_failures = case_failures + 1;
                end
            end

            if (sample_count > 1 && payload_start_cycle >= 0) begin
                actual_offset = sample_cycles[1] - payload_start_cycle;
                expected_offset = bit_period / 2;
                timing_error = actual_offset - expected_offset;

                if (sampled_bits[1] !== 1'b0 ||
                    timing_error < -2 || timing_error > 2) begin
                    $display("START SAMPLE ERROR: period=%0d value=%0b offset=%0d expected=%0d",
                             bit_period, sampled_bits[1],
                             actual_offset, expected_offset);
                    case_failures = case_failures + 1;
                end
            end

            for (b = 0; b < 8; b = b + 1) begin
                if (sample_count > 2+b && payload_start_cycle >= 0) begin
                    expected_bit = payload[b];
                    expected_offset = bit_period + bit_period/2 +
                                      b*bit_period;
                    actual_offset = sample_cycles[2+b] -
                                    payload_start_cycle;
                    timing_error = actual_offset - expected_offset;

                    if (timing_error < 0)
                        abs_error = -timing_error;
                    else
                        abs_error = timing_error;

                    if (abs_error > max_error)
                        max_error = abs_error;

                    if (sampled_bits[2+b] !== expected_bit ||
                        timing_error < -2 || timing_error > 2) begin
                        $display("BIT ERROR: period=%0d payload=0x%02x bit=%0d got=%0b expected=%0d offset=%0d ideal=%0d error=%0d",
                                 bit_period, payload, b,
                                 sampled_bits[2+b], expected_bit,
                                 actual_offset, expected_offset,
                                 timing_error);
                        case_failures = case_failures + 1;
                    end
                end
            end

            if (shift_reg !== payload) begin
                $display("BYTE ERROR: period=%0d payload=0x%02x got=0x%02x expected=0x%02x",
                         bit_period, payload, shift_reg, payload);
                case_failures = case_failures + 1;
            end

            if (fault) begin
                $display("RTL FAULT: period=%0d payload=0x%02x",
                         bit_period, payload);
                case_failures = case_failures + 1;
            end

            if (case_failures == 0)
                $display("PASS: period=%0d payload=0x%02x result=0x%02x max_sample_error=%0d",
                         bit_period, payload, shift_reg, max_error);
            else begin
                $display("FAIL: period=%0d payload=0x%02x failures=%0d",
                         bit_period, payload, case_failures);
                total_failures = total_failures + 1;
            end
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

        for (edge_index = 0; edge_index < 9; edge_index = edge_index + 1) begin
            instructions[p] = (edge_index % 2 == 0) ?
                              16'h4000 : 16'h4001;
            p = p + 1;
        end

        instructions[p] = 16'hC000;
        p = p + 1;
        instructions[p] = 16'h2000;
        p = p + 1;
        instructions[p] = 16'hD000;
        p = p + 1;

        for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin
            instructions[p] = 16'hC000;
            p = p + 1;
            instructions[p] = 16'hC000;
            p = p + 1;
            instructions[p] = 16'h2000;
            p = p + 1;
            instructions[p] = 16'hD000;
            p = p + 1;
        end

        instructions[p] = 16'h0000;

        payloads[0] = 8'h55;
        payloads[1] = 8'hFF;
        payloads[2] = 8'h00;
        payloads[3] = 8'hA6;
        payloads[4] = 8'hC3;
        payloads[5] = 8'h01;

        periods[0] = 20;
        periods[1] = 40;
        periods[2] = 80;
        periods[3] = 120;

        repeat (2) @(negedge clk);
        rst_n = 1'b1;
        program_mode = 1'b1;

        for (j = 0; j <= p; j = j + 1)
            write_word(j[5:0], instructions[j]);

        @(negedge clk);
        program_mode = 1'b0;
        rst_n = 1'b0;

        $display("PROGRAM WORDS: %0d", p + 1);

        for (period_index = 0; period_index < 4; period_index = period_index + 1) begin
            for (j = 0; j < 6; j = j + 1) begin
                $display("TEST: period=%0d payload=0x%02x",
                         periods[period_index], payloads[j]);
                run_case(payloads[j], periods[period_index]);
            end
        end

        $display("MULTI-RATE MATRIX: 24 cases, %0d failures",
                 total_failures);

        if (total_failures != 0)
            $fatal(1, "Multi-rate calibration test failed");

        $display("MULTI-RATE CALIBRATION MATRIX PASS");
        $finish;
    end
endmodule
