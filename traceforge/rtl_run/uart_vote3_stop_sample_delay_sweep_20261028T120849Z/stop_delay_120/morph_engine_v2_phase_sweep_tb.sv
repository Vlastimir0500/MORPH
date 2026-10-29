module morph_engine_v2_diff_tb;

    logic clk = 1'b0;
    logic rst_n = 1'b1;
    logic program_mode = 1'b0;
    logic program_high_byte = 1'b0;
    logic [5:0] program_addr = 6'd0;
    logic [7:0] program_byte = 8'd0;
    logic [7:0] pin_in = 8'd0;
    logic [7:0] pin_out;
    logic [7:0] pin_oe;
    logic sample_reg;
    logic [7:0] shift_reg;
    logic timed_out;
    logic fault;
    logic [15:0] program_image [0:63];
    logic [7:0] pin_vectors [0:8191];
    integer n = 0;
    integer i;
    integer trace_index = 0;

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

    task automatic tick;
        begin
            @(posedge clk);
            #1;
        end
    endtask

    task automatic emit_trace;
        begin
            $display("TRACE %0d %0d %0d %04x %02x %02x %0d %02x %0d %0d %0d",
                trace_index, dut.state, dut.pc, dut.ir, pin_out, pin_oe,
                sample_reg, shift_reg, dut.wait_count, timed_out, fault);
            trace_index = trace_index + 1;
        end
    endtask

    initial begin
        if (!$value$plusargs("N=%d", n))
            $fatal(1, "Missing +N=<count>");

        $readmemh("traceforge/rtl_run/uart_vote3_stop_sample_delay_sweep_20261028T120849Z/stop_delay_120/morph_v2_program.hex", program_image);
        $readmemh("traceforge/rtl_run/uart_vote3_stop_sample_delay_sweep_20261028T120849Z/stop_delay_120/morph_v2_vectors.hex", pin_vectors);

        program_mode = 1'b1;
        for (i = 0; i < 64; i = i + 1) begin
            program_addr = i;
            program_high_byte = 1'b0;
            program_byte = program_image[i][7:0];
            tick();
            program_high_byte = 1'b1;
            program_byte = program_image[i][15:8];
            tick();
        end

        program_mode = 1'b0;
        program_high_byte = 1'b0;
        program_addr = 6'd0;
        program_byte = 8'd0;
        pin_in = 8'd0;
        rst_n = 1'b0;
        tick();
        emit_trace();

        rst_n = 1'b1;
        for (i = 0; i < n; i = i + 1) begin
            pin_in = pin_vectors[i];
            tick();
            emit_trace();
        end

        $finish;
    end

endmodule
