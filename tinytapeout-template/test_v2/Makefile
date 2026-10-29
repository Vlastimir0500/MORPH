TOPLEVEL_LANG = verilog
SIM ?= icarus
VERILOG_SOURCES = $(abspath ../src/project_v2.v) $(abspath ../src/morph_engine_v2.sv) $(abspath tb.v)
TOPLEVEL = tb
MODULE = test_v2
include $(shell cocotb-config --makefiles)/Makefile.sim
