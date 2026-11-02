`timescale 1ns/1ps

module morph_uart_isa_trace_tb;

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
    logic trace_enable = 1'b0;

    integer bit_period = 40;
    integer phase_ns = 5;
    integer prog_idx;
    integer bit_idx;
    logic [7:0] payload = 8'hA5;

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

    integer commit_count = 0;

    always @(posedge clk) begin
        if (!rst_n)
            commit_count <= 0;
        else if (dut.state == 3'd1 && dut.ir[15:12] == 4'hF)
            commit_count <= commit_count + 1;
    end

    always @(posedge clk) begin
        #1;
        if (trace_enable) begin
            $display(
                "TRACE t=%0t pin=%0b prev=%0b state=%0d pc=%0d ir=%04h sample=%0b rx=%02h shift=%02h wait=%0d commit=%0d fault=%0b timeout=%0b",
                $time,
                pin_in[0],
                dut.pin_prev[0],
                dut.state,
                dut.pc,
                dut.ir,
                sample_reg,
                dut.rx_shift_reg,
                shift_reg,
                dut.wait_count,
                commit_count,
                fault,
                timed_out
            );
        end
    end

    task automatic tick;
        begin
            @(posedge clk);
            #1;
        end
    endtask

    task automatic send_uart_frame(input logic [7:0] value);
        begin
            pin_in[0] = 1'b0;
            #(bit_period * 10);

            for (bit_idx = 0; bit_idx < 8; bit_idx = bit_idx + 1) begin
                pin_in[0] = value[bit_idx];
                #(bit_period * 10);
            end

            pin_in[0] = 1'b1;
            #(bit_period * 10);
        end
    endtask

    initial begin
        if (!$value$plusargs("PERIOD=%d", bit_period))
            bit_period = 40;

        if (!$value$plusargs("PHASE=%d", phase_ns))
            phase_ns = 5;

        if (!$value$plusargs("VALUE=%h", payload))
            payload = 8'hA5;

        $display(
            "TRACE_START period=%0d phase_ns=%0d payload=%02h",
            bit_period,
            phase_ns,
            payload
        );

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
        rst_n = 1'b0;
        tick();

        rst_n = 1'b1;
        repeat (12) @(posedge clk);
        #1;

        if (dut.state !== 3'd3)
            $fatal(1, "Receiver did not reach EDGE_WAIT");

        @(posedge clk);
        #(phase_ns);

        trace_enable = 1'b1;
        send_uart_frame(payload);

        repeat (12) @(posedge clk);
        #1;
        trace_enable = 1'b0;

        $display(
            "TRACE_END period=%0d commits=%0d expected=%02h actual=%02h state=%0d",
            bit_period,
            commit_count,
            payload,
            shift_reg,
            dut.state
        );

        $finish;
    end

endmodule
