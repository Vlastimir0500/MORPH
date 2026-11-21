`timescale 1ns/1ps

module morph_uart_isa_negative_tb;

    logic clk = 1'b0;
    logic rst_n = 1'b1;
    logic program_mode = 1'b0;
    logic program_high_byte = 1'b0;
    logic [5:0] program_addr = 6'd0;
    logic [7:0] program_byte = 8'd0;
    logic [7:0] pin_in = 8'hFF;

    logic [7:0] pin_out;
    logic [7:0] pin_oe;
    logic sample_reg;
    logic [7:0] shift_reg;
    logic timed_out;
    logic fault;

    logic [15:0] program_image [0:63];

    integer commit_count = 0;
    integer prog_idx;
    integer frame_idx;
    integer before_count;
    integer payload_value;
    integer bit_period;

    logic [7:0] bad_value;
    logic [7:0] good_value;

    always #5 clk = ~clk;

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

    always @(posedge clk) begin
        if (!rst_n)
            commit_count <= 0;
        else if (dut.state == 3'd1 && dut.ir[15:12] == 4'hF)
            commit_count <= commit_count + 1;
    end

    task automatic tick;
        begin
            @(posedge clk);
            #1;
        end
    endtask

    task automatic reset_receiver;
        begin
            pin_in = 8'hFF;
            rst_n = 1'b0;
            tick();
            rst_n = 1'b1;
            repeat (12) @(posedge clk);
            #1;

            if (dut.state !== 3'd3)
                $fatal(1, "Receiver did not reach EDGE_WAIT");
        end
    endtask

    task automatic wait_for_rearm;
        integer cycle_idx;
        logic found;
        begin
            found = 1'b0;

            for (cycle_idx = 0; cycle_idx < 200; cycle_idx = cycle_idx + 1) begin
                @(posedge clk);
                #1;

                if (dut.state === 3'd3 && pin_in[0] === 1'b1) begin
                    found = 1'b1;
                    cycle_idx = 200;
                end
            end

            if (!found)
                $fatal(1, "Receiver failed to rearm");

            if (fault || timed_out)
                $fatal(1, "Engine fault while rearming");
        end
    endtask

    task automatic send_false_start(input integer low_cycles);
        begin
            pin_in[0] = 1'b0;
            #(low_cycles * 10);
            pin_in[0] = 1'b1;
        end
    endtask

    task automatic send_uart_frame(input logic [7:0] value);
        integer bit_index;
        begin
            pin_in[0] = 1'b0;
            #(bit_period * 10);

            for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin
                pin_in[0] = value[bit_index];
                #(bit_period * 10);
            end

            pin_in[0] = 1'b1;
            #(bit_period * 10);
        end
    endtask

    task automatic send_bad_stop_frame(input logic [7:0] value);
        integer bit_index;
        begin
            pin_in[0] = 1'b0;
            #(bit_period * 10);

            for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin
                pin_in[0] = value[bit_index];
                #(bit_period * 10);
            end

            pin_in[0] = 1'b0;
            #(bit_period * 10);

            pin_in[0] = 1'b1;
            #(bit_period * 10);
        end
    endtask

    initial begin
        $readmemh("program.hex", program_image);

        program_mode = 1'b1;

        for (prog_idx = 0; prog_idx < 64; prog_idx = prog_idx + 1) begin
            program_addr = prog_idx[5:0];
            program_high_byte = 1'b0;
            program_byte = program_image[prog_idx][7:0];
            tick();

            program_high_byte = 1'b1;
            program_byte = program_image[prog_idx][15:8];
            tick();
        end

        program_mode = 1'b0;
        program_high_byte = 1'b0;
        program_addr = 6'd0;
        program_byte = 8'd0;

        bit_period = 40;

        reset_receiver();

        @(posedge clk);
        #1;

        before_count = commit_count;
        send_false_start(8);
        wait_for_rearm();

        if (commit_count != before_count)
            $fatal(1, "False start incorrectly committed");

        $display("FALSE_START_REJECTED");

        send_uart_frame(8'hA5);

        if (commit_count != before_count + 1)
            $fatal(1, "Valid frame after false start was not committed");

        if (dut.shift_reg !== 8'hA5)
            $fatal(1, "Recovery data mismatch after false start");

        wait_for_rearm();

        $display("FALSE_START_RECOVERY_PASSED");

        for (frame_idx = 0; frame_idx < 32; frame_idx = frame_idx + 1) begin
            payload_value = frame_idx * 73 + 41;
            bad_value = payload_value[7:0];
            good_value = bad_value ^ 8'hA5;
            before_count = commit_count;

            send_bad_stop_frame(bad_value);
            wait_for_rearm();

            if (commit_count != before_count)
                $fatal(1, "Bad stop incorrectly committed frame=%0d", frame_idx);

            send_uart_frame(good_value);

            if (commit_count != before_count + 1)
                $fatal(1, "Valid recovery frame not committed frame=%0d", frame_idx);

            if (dut.shift_reg !== good_value)
                $fatal(
                    1,
                    "Recovery data mismatch frame=%0d expected=%02x actual=%02x",
                    frame_idx,
                    good_value,
                    dut.shift_reg
                );

            wait_for_rearm();

            if (fault || timed_out)
                $fatal(1, "Engine fault frame=%0d", frame_idx);
        end

        if (commit_count != 33)
            $fatal(1, "Unexpected total commits=%0d", commit_count);

        $display("BAD_STOP_REJECTIONS_PASSED count=32");
        $display("VALID_RECOVERY_FRAMES_PASSED count=33");
        $display("UART_ISA_RX_NEGATIVE_QUALIFICATION_PASSED");

        $finish;
    end

endmodule
