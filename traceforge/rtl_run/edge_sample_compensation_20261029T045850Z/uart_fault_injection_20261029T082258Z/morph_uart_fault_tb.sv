module morph_uart_fault_tb;
    logic clk = 0;
    logic rst_n = 0;
    logic rx = 1;

    logic [7:0] data_out;
    logic byte_valid;
    logic framing_error;
    logic event_tick;
    logic [3:0] event_index;

    integer cases = 0;
    integer clean_failures = 0;
    integer false_start_failures = 0;
    integer bad_stop_failures = 0;
    integer glitch_failures = 0;

    bit valid_seen = 0;
    bit framing_seen = 0;

    morph_uart_rx_candidate #(.CORRECTION_MODE(1)) dut (
        .clk(clk), .rst_n(rst_n), .rx(rx),
        .data_out(data_out), .byte_valid(byte_valid),
        .framing_error(framing_error),
        .sample_event_tick(event_tick),
        .sample_event_index(event_index)
    );

    always #5 clk = ~clk;

    // STICKY_STATUS_MONITOR: sample status synchronously.
    // Reset these flags through rst_n, not from stimulus-task assignments.
    always @(posedge clk) begin
        if (!rst_n) begin
            valid_seen <= 1'b0;
            framing_seen <= 1'b0;
        end else begin
            if (byte_valid)
                valid_seen <= 1'b1;
            if (framing_error)
                framing_seen <= 1'b1;
        end
    end

    task automatic start_case;
        begin
            rst_n = 0;
            rx = 1;
            repeat (4) @(negedge clk);
            rst_n = 1;
            @(negedge clk);
        end
    endtask

    task automatic send_frame(input logic [7:0] payload, input integer period);
        integer b;
        begin
            rx = 0;
            repeat (period) @(negedge clk);

            for (b = 0; b < 8; b = b + 1) begin
                rx = payload[b];
                repeat (period) @(negedge clk);
            end

            rx = 1;
            repeat (period + 8) @(negedge clk);
        end
    endtask

    task automatic send_bad_stop(input logic [7:0] payload, input integer period);
        integer b;
        begin
            rx = 0;
            repeat (period) @(negedge clk);

            for (b = 0; b < 8; b = b + 1) begin
                rx = payload[b];
                repeat (period) @(negedge clk);
            end

            // Deliberately invalid low stop bit.
            rx = 0;
            repeat (period) @(negedge clk);

            rx = 1;
            repeat (period + 10) @(negedge clk);
        end
    endtask

    task automatic send_false_start;
        begin
            // A short six-cycle low pulse, not a valid start bit.
            rx = 0;
            repeat (6) @(negedge clk);
            rx = 1;
            repeat (60) @(negedge clk);
        end
    endtask

    task automatic send_glitched_frame(
        input logic [7:0] payload,
        input integer period,
        input integer glitch_offset
    );
        integer b;
        begin
            rx = 0;
            repeat (period) @(negedge clk);

            // Bit 0 is high in payload FF. Inject a one-cycle low glitch.
            rx = payload[0];
            repeat (glitch_offset) @(negedge clk);
            rx = 0;
            repeat (1) @(negedge clk);
            rx = payload[0];
            repeat (period - glitch_offset - 1) @(negedge clk);

            for (b = 1; b < 8; b = b + 1) begin
                rx = payload[b];
                repeat (period) @(negedge clk);
            end

            rx = 1;
            repeat (period + 10) @(negedge clk);
        end
    endtask

    initial begin
        $display("MORPH isolated hard-reanchor UART fault injection");
        $display("Nominal bit period = 40 cycles");
        $display("");

        // Control: an ordinary valid frame must pass.
        start_case();
        send_frame(8'hA6, 40);
        cases = cases + 1;

        if (valid_seen && !framing_seen && data_out == 8'hA6)
            $display("PASS clean control: payload A6 decoded");
        else begin
            $display("FAIL clean control: got=%02x valid=%0d framing=%0d",
                     data_out, valid_seen, framing_seen);
            clean_failures = clean_failures + 1;
        end

        // A short false start must not create a byte.
        start_case();
        send_false_start();
        cases = cases + 1;

        if (!valid_seen && !framing_seen)
            $display("PASS short false start rejected");
        else begin
            $display("FAIL short false start: valid=%0d framing=%0d",
                     valid_seen, framing_seen);
            false_start_failures = false_start_failures + 1;
        end

        // A low stop bit should raise framing_error.
        start_case();
        send_bad_stop(8'hA6, 40);
        cases = cases + 1;

        if (framing_seen && !valid_seen)
            $display("PASS malformed stop flagged");
        else begin
            $display("FAIL malformed stop: valid=%0d framing=%0d",
                     valid_seen, framing_seen);
            bad_stop_failures = bad_stop_failures + 1;
        end

        // Put a one-cycle glitch into a high data bit at several offsets.
        for (integer offset = 8; offset <= 28; offset = offset + 4) begin
            start_case();
            send_glitched_frame(8'hFF, 40, offset);
            cases = cases + 1;

            if (valid_seen && !framing_seen && data_out == 8'hFF)
                $display("PASS single-cycle data glitch at offset=%0d", offset);
            else begin
                $display(
                    "FAIL single-cycle data glitch offset=%0d got=%02x valid=%0d framing=%0d",
                    offset, data_out, valid_seen, framing_seen
                );
                glitch_failures = glitch_failures + 1;
            end
        end

        $display("");
        $display(
            "SUMMARY cases=%0d clean_failures=%0d false_start_failures=%0d bad_stop_failures=%0d glitch_failures=%0d",
            cases, clean_failures, false_start_failures,
            bad_stop_failures, glitch_failures
        );

        if (clean_failures != 0 ||
            false_start_failures != 0 ||
            bad_stop_failures != 0 ||
            glitch_failures != 0)
            $fatal(1, "UART fault-injection suite failed");

        $display("UART FAULT-INJECTION SUITE PASS");
        $finish;
    end

    // DBG_STATE_TRACE: temporary internal trace for first clean frame only.
    integer dbg_last_state = -1;
    integer dbg_cycle_counter = 0;

    always @(negedge clk) begin
        dbg_cycle_counter = dbg_cycle_counter + 1;
        if (!rst_n) begin
            dbg_last_state = -1;
        end else if (cases == 0) begin
            if ((dut.state != dbg_last_state) ||
                (dut.state >= 4'd7)) begin
                $display(
                    "DBG_STATE_TRACE cycle=%0d state=%0d timer=%0d bit=%0d rx=%b prev=%b early=%b center=%b majority=%b data=%02x valid=%b frame_error=%b",
                    dbg_cycle_counter, dut.state, dut.timer, dut.bit_index,
                    rx, dut.pin_prev, dut.sample_early,
                    dut.sample_center, dut.majority_value, data_out,
                    byte_valid, framing_error
                );
            end

            dbg_last_state = dut.state;

            if (byte_valid || framing_error) begin
                $display(
                    "DBG_OUTPUT cycle=%0d valid=%b framing_error=%b data=%02x",
                    dbg_cycle_counter, byte_valid, framing_error, data_out
                );
            end
        end
    end

endmodule
