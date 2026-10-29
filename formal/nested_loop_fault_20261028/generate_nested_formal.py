from pathlib import Path
from morph_assembler_v2 import assemble

source = """outer: DRIVE 0, 1
inner: DRIVE 1, 1
LOOP 2, inner
LOOP 2, outer
HALT
"""
words = assemble(source)
cases = "\n".join(
    f"                6'd{i}: program_word = 16'h{word:04X};"
    for i, word in enumerate(words)
)

template = """module morph_nested_loop_formal(input logic clk);
    logic [5:0] phase = 6'd0;
    logic reset_seen = 1'b0;
    logic fault_seen = 1'b0;

    wire rst_n = phase != 6'd0;
    wire program_mode = phase >= 6'd1 && phase <= 6'd12;
    wire program_high_byte = phase[0];
    wire [5:0] program_addr = (phase - 6'd1) >> 1;
    wire [15:0] selected_word = program_word(program_addr);
    wire [7:0] program_byte =
        program_high_byte ? selected_word[15:8] : selected_word[7:0];

    wire [7:0] pin_in = 8'd0;
    logic [7:0] pin_out;
    logic [7:0] pin_oe;
    logic sample_reg;
    logic [7:0] shift_reg;
    logic timed_out;
    logic fault;

    function automatic [15:0] program_word(input [5:0] addr);
        begin
            case (addr)
__CASES__
                default: program_word = 16'h0000;
            endcase
        end
    endfunction

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

    always_ff @(posedge clk) begin
        if (!rst_n)
            reset_seen <= 1'b1;

        if (phase < 6'd40)
            phase <= phase + 1'b1;

        if (reset_seen && rst_n && fault) begin
            assert(pin_oe == 8'd0);
            fault_seen <= 1'b1;
        end

        if (fault_seen) begin
            assert(fault);
            assert(pin_oe == 8'd0);
        end

        if (phase == 6'd32) begin
            assert(reset_seen);
            assert(fault_seen);
            assert(fault);
            assert(pin_oe == 8'd0);
        end
    end
endmodule
"""

Path("morph_nested_loop_formal.sv").write_text(
    template.replace("__CASES__", cases) + "\n"
)

print("ASSEMBLED PROGRAM:")
for i, word in enumerate(words):
    print(f"{i:02d}: 0x{word:04X}")
print("FORMAL HARNESS CREATED")
