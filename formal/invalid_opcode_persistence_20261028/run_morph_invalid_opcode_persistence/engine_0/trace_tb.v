`ifndef VERILATOR
module testbench;
  reg [4095:0] vcdfile;
  reg clock;
`else
module testbench(input clock, output reg genclock);
  initial genclock = 1;
`endif
  reg genclock = 1;
  reg [31:0] cycle = 0;
  wire [0:0] PI_clk = clock;
  morph_invalid_opcode_formal UUT (
    .clk(PI_clk)
  );
`ifndef VERILATOR
  initial begin
    if ($value$plusargs("vcd=%s", vcdfile)) begin
      $dumpfile(vcdfile);
      $dumpvars(0, testbench);
    end
    #5 clock = 0;
    while (genclock) begin
      #5 clock = 0;
      #5 clock = 1;
    end
  end
`endif
  initial begin
`ifndef VERILATOR
    #1;
`endif
    // UUT.$auto$async2sync.\cc:107:execute$1152  = 1'b0;
    // UUT.$auto$async2sync.\cc:107:execute$1164  = 1'b0;
    // UUT.$auto$async2sync.\cc:107:execute$1170  = 1'b0;
    // UUT.$auto$async2sync.\cc:107:execute$1182  = 1'b0;
    // UUT.$auto$async2sync.\cc:116:execute$1168  = 1'b1;
    // UUT.$auto$async2sync.\cc:116:execute$1174  = 1'b1;
    // UUT.$auto$async2sync.\cc:116:execute$1186  = 1'b1;
    UUT.done = 1'b0;
    UUT.dut.fault = 1'b1;
    UUT.dut.ir = 16'b0000000000000000;
    UUT.dut.loop_active = 1'b0;
    UUT.dut.loop_pc = 6'b000000;
    UUT.dut.loop_remaining = 6'b000000;
    UUT.dut.loop_target = 6'b000000;
    UUT.dut.pc = 6'b000000;
    UUT.dut.pin_oe = 8'b00000001;
    UUT.dut.pin_out = 8'b00000000;
    UUT.dut.pin_prev = 8'b00000000;
    UUT.dut.sample_reg = 1'b1;
    UUT.dut.shift_reg = 8'b00000000;
    UUT.dut.state = 3'b000;
    UUT.dut.timed_out = 1'b1;
    UUT.dut.wait_count = 8'b00000000;
    UUT.phase = 4'b0000;
    UUT.dut.prog_mem[6'b000000] = 16'b0000000000000000;

    // state 0
  end
  always @(posedge clock) begin
    // state 1
    if (cycle == 0) begin
    end

    genclock <= cycle < 1;
    cycle <= cycle + 1;
  end
endmodule
