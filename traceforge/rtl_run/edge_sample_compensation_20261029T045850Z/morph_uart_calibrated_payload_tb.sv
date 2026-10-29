
module morph_uart_calibrated_payload_tb;
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

    logic [15:0] instructions [0:17];
    logic [7:0] payloads [0:5];
    integer cycle_count = 0;
    integer sample_count = 0;
    integer sample_cycles [0:16];
    logic sampled_bits [0:16];
    integer capture_cycle = -1;
    integer payload_start_cycle = -1;
    integer total_failures = 0;

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

            if (payload_start_cycle < 0 &&
                dut.state == 3'd3 &&
                dut.ir[15:12] == 4'h4 &&
                dut.pin_prev[0] &&
                !pin_in[0])
                payload_start_cycle = cycle_count;

            if (sample_count < 17 &&
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
            repeat (40) @(negedge clk);

            for (b = 0; b < 8; b = b + 1) begin
                pin_in[0] = data[b];
                repeat (40) @(negedge clk);
            end

            pin_in[0] = 1'b1;
            repeat (40) @(negedge clk);
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

    task automatic run_case(input logic [7:0] payload);
        integer errors;
        integer b;
        integer offset;
        integer expected;
        integer timing_error;
        begin
            @(negedge clk);
            rst_n = 1'b0;
            pin_in = 8'd1;
            sample_count = 0;
            capture_cycle = -1;
            payload_start_cycle = -1;

            repeat (2) @(negedge clk);
            rst_n = 1'b1;
            repeat (8) @(posedge clk);

            send_uart_byte(8'h55);
            send_uart_byte(payload);

            repeat (100) @(posedge clk);
            #1;

            errors = 0;

            if (sample_count != 17) begin
                $display("SAMPLE COUNT ERROR: got=%0d expected=17", sample_count);
                errors = errors + 1;
            end

            if (!dut.edge_capture_valid || dut.edge_interval != 40) begin
                $display("CALIBRATION ERROR: valid=%0b interval=%0d",
                         dut.edge_capture_valid, dut.edge_interval);
                errors = errors + 1;
            end

            if (capture_cycle < 0 || payload_start_cycle < 0) begin
                $display("MISSING CAPTURE OR PAYLOAD START EVENT");
                errors = errors + 1;
            end

            for (b = 0; b < 8; b = b + 1) begin
                if (sample_count > b) begin
                    expected = (b % 2 == 0) ? 1 : 0;
                    offset = sample_cycles[b] - capture_cycle;
                    timing_error = offset - (20 + 40*b);

                    if (sampled_bits[b] !== expected || timing_error < -2 || timing_error > 2) begin
                        $display("CALIBRATION BIT %0d: value=%0b expected=%0d offset=%0d",
                                 b, sampled_bits[b], expected, offset);
                        errors = errors + 1;
                    end
                end
            end

            if (sample_count > 8) begin
                offset = sample_cycles[8] - payload_start_cycle;

                if (sampled_bits[8] !== 1'b0 || offset < 18 || offset > 22) begin
                    $display("START SAMPLE ERROR: value=%0b offset=%0d",
                             sampled_bits[8], offset);
                    errors = errors + 1;
                end
            end

            for (b = 0; b < 8; b = b + 1) begin
                if (sample_count > 9+b) begin
                    expected = payload[b];
                    offset = sample_cycles[9+b] - payload_start_cycle;
                    timing_error = offset - (60 + 40*b);

                    $display("PAYLOAD BIT %0d: got=%0b expected=%0d offset=%0d ideal=%0d error=%0d",
                             b, sampled_bits[9+b], expected,
                             offset, 60 + 40*b, timing_error);

                    if (sampled_bits[9+b] !== expected ||
                        timing_error < -2 || timing_error > 2)
                        errors = errors + 1;
                end
            end

            if (shift_reg !== reverse_byte(payload)) begin
                $display("BYTE ERROR: got=0x%02x expected=0x%02x",
                         shift_reg, reverse_byte(payload));
                errors = errors + 1;
            end

            if (fault) begin
                $display("UNEXPECTED RTL FAULT");
                errors = errors + 1;
            end

            if (errors == 0)
                $display("CALIBRATED PAYLOAD PASS: 0x%02x -> 0x%02x",
                         payload, shift_reg);
            else begin
                $display("CALIBRATED PAYLOAD FAIL: 0x%02x, errors=%0d",
                         payload, errors);
                total_failures = total_failures + 1;
            end
        end
    endtask

    integer j;

    initial begin
        instructions[0] = 16'hB002;
        instructions[1] = 16'hC000;
        instructions[2] = 16'h2000;
        instructions[3] = 16'h5000;
        instructions[4] = 16'hC000;
        instructions[5] = 16'hC000;
        instructions[6] = 16'h2000;
        instructions[7] = 16'h5000;
        instructions[8] = 16'h91C4;
        instructions[9] = 16'h4000;
        instructions[10] = 16'hC000;
        instructions[11] = 16'h2000;
        instructions[12] = 16'hC000;
        instructions[13] = 16'hC000;
        instructions[14] = 16'h2000;
        instructions[15] = 16'h5000;
        instructions[16] = 16'h920C;
        instructions[17] = 16'h0000;

        payloads[0] = 8'h55;
        payloads[1] = 8'hFF;
        payloads[2] = 8'h00;
        payloads[3] = 8'hA6;
        payloads[4] = 8'hC3;
        payloads[5] = 8'h01;

        repeat (2) @(negedge clk);
        rst_n = 1'b1;
        program_mode = 1'b1;

        for (j = 0; j < 18; j = j + 1)
            write_word(j[5:0], instructions[j]);

        @(negedge clk);
        program_mode = 1'b0;
        rst_n = 1'b0;

        for (j = 0; j < 6; j = j + 1) begin
            $display("\n===== CALIBRATION 0x55, PAYLOAD 0x%02x =====",
                     payloads[j]);
            run_case(payloads[j]);
        end

        $display("\nCALIBRATED PAYLOAD MATRIX: 6 cases, %0d failures",
                 total_failures);

        if (total_failures == 0)
            $display("CALIBRATED PAYLOAD MATRIX PASS");

        $finish;
    end
endmodule
