`default_nettype none

module tt_um_rattandeep_morph_v2 (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

    wire program_mode = ui_in[7];
    wire program_high_byte = ui_in[6];
    wire [5:0] program_addr = ui_in[5:0];

    wire [7:0] engine_pin_out;
    wire [7:0] engine_pin_oe;
    wire engine_sample;
    wire [7:0] engine_shift;
    wire engine_timed_out;
    wire engine_fault;

    morph_engine_v2 engine (
        .clk(clk),
        .rst_n(rst_n),
        .program_mode(program_mode),
        .program_high_byte(program_high_byte),
        .program_addr(program_addr),
        .program_byte(uio_in),
        .pin_in(uio_in),
        .pin_out(engine_pin_out),
        .pin_oe(engine_pin_oe),
        .sample_reg(engine_sample),
        .shift_reg(engine_shift),
        .timed_out(engine_timed_out),
        .fault(engine_fault)
    );

    assign uio_out = engine_pin_out;
    assign uio_oe = (ena && rst_n && !program_mode) ? engine_pin_oe : 8'h00;
    wire trace_read_mode = !program_mode && ui_in[6];
    wire [7:0] trace_byte;
    wire [7:0] trace_status;

    morph_x_trace_capture trace_engine (
        .clk(clk), .rst_n(rst_n), .enable(ena),
        .program_mode(program_mode), .read_mode(trace_read_mode),
        .sample_pins(uio_in), .read_slot(ui_in[2:0]),
        .read_page(ui_in[4:3]), .read_data(trace_byte),
        .status(trace_status)
    );

    assign uo_out = trace_read_mode ?
                    (ui_in[5] ? trace_status : trace_byte) : engine_shift;

    wire _unused = &{engine_sample, engine_timed_out, engine_fault, 1'b0};

endmodule

`default_nettype wire
