module morph_edge_wrap_tb;
    logic clk = 1'b0;
    logic rst_n = 1'b0;
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
    integer periods [0:2];
    integer first_cycle_value;

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

    task automatic write_word(input logic [5:0] address, input logic [15:0] instruction);
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

    initial begin
        periods[0] = 430;
        periods[1] = 463;
        periods[2] = 407;

        repeat (2) @(negedge clk);
        rst_n = 1'b1;
        program_mode = 1'b1;
        write_word(6'd0, 16'hB002);
        write_word(6'd1, 16'h6000);

        @(negedge clk);
        program_mode = 1'b0;
        rst_n = 1'b0;
        repeat (2) @(negedge clk);
        rst_n = 1'b1;

        repeat (8) @(posedge clk);
        #1;

        if (dut.state != 3'd3) $fatal(1, "Capture instruction did not start");

        repeat (65300) @(posedge clk);
        #1;

        @(negedge clk);
        pin_in[0] = 1'b1;
        @(posedge clk);
        #1;

        if (!dut.edge_seen) $fatal(1, "Initial edge was not captured");

        first_cycle_value = dut.edge_last_cycle;

        if (first_cycle_value + periods[0] < 65536)
            $fatal(1, "First measurement will not cross counter rollover");

        for (int i = 1; i <= periods[0]; i++) begin
            @(negedge clk);
            if (i == periods[0]) pin_in[0] = 1'b0;
        end

        @(posedge clk);
        #1;

        if (!dut.edge_capture_valid) $fatal(1, "First interval was not marked valid");
        if (dut.edge_interval != 16'd430)
            $fatal(1, "Rollover interval expected 430, got %0d", dut.edge_interval);

        $display("RTL PASS: rollover interval %0d cycles", dut.edge_interval);

        for (int i = 1; i <= periods[1]; i++) begin
            @(negedge clk);
            if (i == periods[1]) pin_in[0] = 1'b1;
        end

        @(posedge clk);
        #1;

        if (dut.edge_interval != 16'd463)
            $fatal(1, "Second interval expected 463, got %0d", dut.edge_interval);

        $display("RTL PASS: successive interval %0d cycles", dut.edge_interval);

        for (int i = 1; i <= periods[2]; i++) begin
            @(negedge clk);
            if (i == periods[2]) pin_in[0] = 1'b0;
        end

        @(posedge clk);
        #1;

        if (dut.edge_interval != 16'd407)
            $fatal(1, "Third interval expected 407, got %0d", dut.edge_interval);

        if (fault) $fatal(1, "Unexpected RTL fault");

        $display("RTL PASS: successive interval %0d cycles", dut.edge_interval);
        $display("EDGE CAPTURE ROLLOVER TEST PASS");
        $finish;
    end
endmodule
