`default_nettype none

module tt_um_rattandeep_morph (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

wire program_mode = ui_in[6];
wire byte_write = ui_in[4];
wire high_byte = ui_in[5];

reg [7:0] program_low_byte;
reg [3:0] program_address;
reg program_low_valid;

wire engine_prog_we = rst_n && program_mode &&
                      byte_write && high_byte && program_low_valid;
wire [15:0] engine_prog_data = {uio_in, program_low_byte};

wire engine_pin_out;
wire engine_sample;
wire [7:0] engine_shift;

always @(posedge clk) begin
    if (!rst_n) begin
        program_low_byte <= 8'h00;
        program_address <= 4'h0;
        program_low_valid <= 1'b0;
    end else if (program_mode && byte_write) begin
        if (!high_byte) begin
            program_low_byte <= uio_in;
            program_address <= ui_in[3:0];
            program_low_valid <= 1'b1;
        end else if (program_low_valid) begin
            program_low_valid <= 1'b0;
        end
    end
end

morph_engine engine (
    .clk(clk),
    .rst_n(rst_n),
    .prog_we(engine_prog_we),
    .prog_addr(program_address),
    .prog_data(engine_prog_data),
    .pin_in(uio_in[0]),
    .pin_out(engine_pin_out),
    .sample_reg(engine_sample),
    .shift_reg(engine_shift)
);

assign uo_out = engine_shift;
assign uio_out = {7'b0000000, engine_pin_out};
assign uio_oe = (ena && rst_n && !program_mode) ? 8'b00000001 : 8'b00000000;

wire _unused = &{ui_in[7], engine_sample, 1'b0};

endmodule

`default_nettype wire
