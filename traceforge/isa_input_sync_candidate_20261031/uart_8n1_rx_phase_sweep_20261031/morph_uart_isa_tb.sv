`timescale 1ns/1ps

module morph_uart_isa_tb;

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

        bit_period = 40;

        for (phase_ns = 1; phase_ns <= 9; phase_ns = phase_ns + 1) begin
            reset_receiver();

            @(posedge clk);
            #(phase_ns);

            for (frame_idx = 0; frame_idx < 256; frame_idx = frame_idx + 1) begin
                before_count = commit_count;

                send_uart_frame(frame_idx[7:0]);

                if (commit_count != before_count + 1)
                    $fatal(
                        1,
                        "Commit mismatch phase=%0d frame=%0d commits=%0d",
                        phase_ns,
                        frame_idx,
                        commit_count
                    );

                if (dut.shift_reg !== frame_idx[7:0])
                    $fatal(
                        1,
                        "Data mismatch phase=%0d expected=%02x actual=%02x",
                        phase_ns,
                        frame_idx[7:0],
                        dut.shift_reg
                    );

                if (fault || timed_out)
                    $fatal(
                        1,
                        "Engine fault phase=%0d frame=%0d",
                        phase_ns,
                        frame_idx
                    );

                if (dut.state !== 3'd3)
                    $fatal(
                        1,
                        "Receiver not rearmed phase=%0d frame=%0d state=%0d",
                        phase_ns,
                        frame_idx,
                        dut.state
                    );
            end

            $display(
                "PHASE_PASS phase_ns=%0d frames=256",
                phase_ns
            );
        end

        $display(
            "UART_ISA_RX_SUMMARY phases=9 expected_frames=2304 commits=%0d",
            9 * 256
        );
        $display("UART_ISA_RX_QUALIFICATION_PASSED");

        $finish;
    end

endmodule
