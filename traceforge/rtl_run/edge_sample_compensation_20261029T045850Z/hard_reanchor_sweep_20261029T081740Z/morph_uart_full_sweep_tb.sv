module morph_uart_full_sweep_tb;
    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic rx = 1'b1;

    logic [7:0] data_out;
    logic byte_valid;
    logic framing_error;
    logic event_tick;
    logic [3:0] event_index;

    integer cycle_count = 0;
    logic edge_prev = 1'b1;
    integer edge_count = 0;
    integer edge_cycles [0:31];

    integer event_count = 0;
    integer sample_centers [0:9];
    bit sample_seen [0:9];

    bit valid_seen = 0;
    bit framing_seen = 0;

    integer total_cases = 0;
    integer decode_failures = 0;
    integer sample_count_errors = 0;
    integer outside_samples = 0;
    integer framing_anomalies = 0;

    integer j;
    integer k;
    integer payload_num;
    integer tx_period;
    integer start_cycle;
    integer cell_start;
    integer offset_cycles;
    integer case_outside;
    integer case_sample_errors;
    integer case_decode_error;

    logic [7:0] payload;

    morph_uart_rx_candidate #(
        .CORRECTION_MODE(1)
    ) hard_receiver (
        .clk(clk),
        .rst_n(rst_n),
        .rx(rx),
        .data_out(data_out),
        .byte_valid(byte_valid),
        .framing_error(framing_error),
        .sample_event_tick(event_tick),
        .sample_event_index(event_index)
    );

    always #5 clk = ~clk;

    // Passive timestamp oracle: record observed input transitions.
    always @(posedge clk) begin
        cycle_count = cycle_count + 1;

        if (!rst_n) begin
            edge_prev = rx;
        end else begin
            if (rx != edge_prev) begin
                if (edge_count < 32)
                    edge_cycles[edge_count] = cycle_count;
                edge_count = edge_count + 1;
            end
            edge_prev = rx;
        end
    end

    // Event index 0 is the start-bit sample; 1..8 are data bits.
    // event_tick marks the third sample; estimate the center two clocks earlier.
    always @(negedge clk) begin
        if (rst_n) begin
            if (event_tick) begin
                event_count = event_count + 1;

                if (event_index < 10) begin
                    sample_centers[event_index] = cycle_count - 2;
                    sample_seen[event_index] = 1'b1;
                end
            end

            if (byte_valid)
                valid_seen = 1'b1;

            if (framing_error)
                framing_seen = 1'b1;
        end
    end

    task automatic send_frame(
        input logic [7:0] value,
        input integer period
    );
        integer b;
        begin
            @(negedge clk);
            rx = 1'b0;
            repeat (period) @(negedge clk);

            for (b = 0; b < 8; b = b + 1) begin
                rx = value[b];
                repeat (period) @(negedge clk);
            end

            rx = 1'b1;
            repeat (period) @(negedge clk);
        end
    endtask

    task automatic run_case(
        input logic [7:0] value,
        input integer period
    );
        integer b;
        begin
            // Reset the receiver and clear observations for this frame.
            rst_n = 1'b0;
            rx = 1'b1;
            repeat (3) @(negedge clk);

            edge_count = 0;
            event_count = 0;
            valid_seen = 1'b0;
            framing_seen = 1'b0;

            for (b = 0; b < 10; b = b + 1) begin
                sample_seen[b] = 1'b0;
                sample_centers[b] = -9999;
            end

            rst_n = 1'b1;
            @(negedge clk);

            send_frame(value, period);
            repeat (25) @(negedge clk);

            total_cases = total_cases + 1;
            case_sample_errors = 0;
            case_outside = 0;
            case_decode_error = 0;

            if (edge_count < 1 || event_count != 10)
                case_sample_errors = case_sample_errors + 1;

            for (b = 0; b < 10; b = b + 1) begin
                if (!sample_seen[b])
                    case_sample_errors = case_sample_errors + 1;
            end

            if (edge_count < 1) begin
                case_outside = 8;
                start_cycle = -9999;
            end else begin
                start_cycle = edge_cycles[0];

                // Data bit b occupies:
                // [start_edge + (b+1)*period,
                //  start_edge + (b+2)*period).
                for (b = 0; b < 8; b = b + 1) begin
                    if (sample_seen[b+1]) begin
                        cell_start = start_cycle + ((b+1) * period);
                        offset_cycles = sample_centers[b+1] - cell_start;

                        if (offset_cycles < 0 || offset_cycles >= period)
                            case_outside = case_outside + 1;
                    end
                end
            end

            if (!valid_seen || framing_seen || data_out !== value)
                case_decode_error = 1;

            if (case_sample_errors != 0)
                sample_count_errors = sample_count_errors + 1;

            outside_samples = outside_samples + case_outside;

            if (case_decode_error != 0)
                decode_failures = decode_failures + 1;

            if (case_decode_error != 0 ||
                case_sample_errors != 0 ||
                case_outside != 0) begin
                $display(
                    "FAIL txT=%0d payload=0x%02x got=0x%02x valid=%0d framing=%0d events=%0d missing=%0d outside=%0d",
                    period, value, data_out, valid_seen, framing_seen,
                    event_count, case_sample_errors, case_outside
                );
            end
        end
    endtask

    initial begin
        $display("MORPH hard-reanchor exhaustive byte sweep");
        $display("Receiver nominal bit period: 40 cycles");
        $display("Transmitter periods: 38, 40, 42 cycles (plus/minus 5 percent)");
        $display("Payloads: all 256 values for each period");
        $display("Checks: decoded value, framing, sample count and data-cell centers");
        $display("");

        for (k = 0; k < 3; k = k + 1) begin
            case (k)
                0: tx_period = 38;
                1: tx_period = 40;
                default: tx_period = 42;
            endcase

            for (payload_num = 0; payload_num < 256; payload_num = payload_num + 1) begin
                payload = payload_num[7:0];
                run_case(payload, tx_period);
            end

            $display("PERIOD COMPLETE: txT=%0d cases=256", tx_period);
        end

        $display("");
        $display(
            "SUMMARY cases=%0d decode_failures=%0d sample_count_errors=%0d outside_data_centers=%0d framing_anomalies=%0d",
            total_cases, decode_failures, sample_count_errors,
            outside_samples, framing_anomalies
        );

        if (total_cases != 768 ||
            decode_failures != 0 ||
            sample_count_errors != 0 ||
            outside_samples != 0) begin
            $fatal(1, "Hard-reanchor exhaustive sweep failed.");
        end

        $display("HARD-REANCHOR EXHAUSTIVE SWEEP PASS");
        $finish;
    end
endmodule
