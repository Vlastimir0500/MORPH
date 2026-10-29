module morph_engine_diff_tb;

    logic clk;
    logic rst_n;
    logic prog_we;
    logic [3:0] prog_addr;
    logic [15:0] prog_data;
    logic pin_in;
    logic pin_out;
    logic sample_reg;
    logic [7:0] shift_reg;

    logic [15:0] program_words [0:15];
    logic [1:0] vectors [0:255];

    integer vector_count;
    integer i;

    morph_engine dut (
        .clk(clk),
        .rst_n(rst_n),
        .prog_we(prog_we),
        .prog_addr(prog_addr),
        .prog_data(prog_data),
        .pin_in(pin_in),
        .pin_out(pin_out),
        .sample_reg(sample_reg),
        .shift_reg(shift_reg)
    );

    always #5 clk = ~clk;

    initial begin
        clk = 0;
        rst_n = 0;
        prog_we = 0;
        prog_addr = 0;
        prog_data = 0;
        pin_in = 0;

        if (!$value$plusargs("N=%d", vector_count))
            $fatal(1, "Missing vector count argument");

        if (vector_count < 1 || vector_count > 256)
            $fatal(1, "Invalid vector count");

        $readmemh("build/rtl_diff_program.hex", program_words);
        $readmemh("build/rtl_diff_vectors.hex", vectors);

        for (i = 0; i < 16; i = i + 1) begin
            @(negedge clk);
            prog_addr = i[3:0];
            prog_data = program_words[i];
            prog_we = 1;

            @(posedge clk);
            #1;
        end

        @(negedge clk);
        prog_we = 0;

        for (i = 0; i < vector_count; i = i + 1) begin
            @(negedge clk);
            rst_n = vectors[i][1];
            pin_in = vectors[i][0];

            @(posedge clk);
            #1;

            $display(
                "TRACE %0d %0d %0d %04h %0d %0d %02h %0d",
                i,
                dut.state,
                dut.pc,
                dut.ir,
                pin_out,
                sample_reg,
                shift_reg,
                dut.wait_count
            );
        end

        $finish;
    end

endmodule
