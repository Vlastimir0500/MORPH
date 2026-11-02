`timescale 1ns/1ps

module morph_uart_isa_generated_tb;

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
    integer phase_ns;
    integer before_count;
    integer bit_period;
    integer plusarg_ok;
    integer commit_errors;
    integer data_errors;
    integer rearm_errors;
    integer engine_errors;
    integer failed_streams;

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

    initial begin
        plusarg_ok = $value$plusargs("BIT_PERIOD=%d", bit_period);

        if (plusarg_ok == 0 || bit_period < 1)
            $fatal(1, "Pass +BIT_PERIOD=<cycles>");

        $display("GENERATED_UART_TEST period=%0d", bit_period);

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
        pin_in = 8'hFF;

        failed_streams = 0;

        for (phase_ns = 1; phase_ns <= 9; phase_ns = phase_ns + 1) begin
            reset_receiver();

            @(posedge clk);
            #(phase_ns);

            commit_errors = 0;
            data_errors = 0;
            rearm_errors = 0;
            engine_errors = 0;

            for (frame_idx = 0; frame_idx < 256; frame_idx = frame_idx + 1) begin
                before_count = commit_count;

                send_uart_frame(frame_idx[7:0]);

                if (commit_count != before_count + 1)
                    commit_errors = commit_errors + 1;

                if (dut.shift_reg !== frame_idx[7:0])
                    data_errors = data_errors + 1;

                if (dut.state !== 3'd3)
                    rearm_errors = rearm_errors + 1;

                if (fault || timed_out)
                    engine_errors = engine_errors + 1;
            end

            if (commit_errors + data_errors + rearm_errors + engine_errors == 0) begin
                $display(
                    "BAUD_CASE period=%0d phase_ns=%0d frames=256 result=PASS",
                    bit_period,
                    phase_ns
                );
            end else begin
                failed_streams = failed_streams + 1;
                $display(
                    "BAUD_CASE period=%0d phase_ns=%0d frames=256 commit_errors=%0d data_errors=%0d rearm_errors=%0d engine_errors=%0d result=FAIL",
                    bit_period,
                    phase_ns,
                    commit_errors,
                    data_errors,
                    rearm_errors,
                    engine_errors
                );
            end
        end

        $display(
            "UART_ISA_GENERATED_SUMMARY period=%0d phases=9 failed_streams=%0d",
            bit_period,
            failed_streams
        );

        if (failed_streams != 0)
            $fatal(1, "UART_ISA_GENERATED_QUALIFICATION_FAILED");

        $display("UART_ISA_GENERATED_QUALIFICATION_PASSED");
        $finish;
    end

endmodule
