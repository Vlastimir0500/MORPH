# TRACEFORGE â€” UART Boundary Cycle Diagnostic v0.1

- Status: **PASS**
- Cases: 7; RTL/reference-model mismatches: 0
- Known counterexample vector exact match: **True**
- Production RTL unchanged: **True**

## Results

| Low-run delta | Low-run duration | Classification | RTL/model match | Trace rows | Event rows |
|---:|---:|---|---|---:|---:|
| -218 | 3706 | silent_misdecode | True | 4393 | 47 |
| -217 | 3707 | silent_misdecode | True | 4394 | 47 |
| -216 | 3708 | silent_misdecode | True | 4395 | 47 |
| -215 | 3709 | correct_decode | True | 4396 | 47 |
| -214 | 3710 | correct_decode | True | 4397 | 47 |
| -213 | 3711 | correct_decode | True | 4398 | 48 |
| 0 | 3924 | correct_decode | True | 4611 | 51 |

## Boundary event excerpts

| Delta | Trace index | Relative to input edge | Input | State | PC | Instruction | Sample | Shift register | Event tags |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| -217 | 227 | -3491 | 0 | 0 | 2 | 0x30D6 | 0 | 0x00 | sample_instruction_state_transition |
| -217 | 228 | -3490 | 0 | 1 | 2 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -217 | 665 | -3053 | 0 | 0 | 6 | 0x30D7 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -217 | 666 | -3052 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -217 | 1101 | -2617 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -217 | 1102 | -2616 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -217 | 1537 | -2181 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -217 | 1538 | -2180 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -217 | 1973 | -1745 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -217 | 1974 | -1744 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -217 | 2409 | -1309 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -217 | 2410 | -1308 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -217 | 2845 | -873 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -217 | 2846 | -872 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -217 | 3281 | -437 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -217 | 3282 | -436 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -217 | 3715 | -3 | 0 | 0 | 10 | 0x30D5 | 0 | 0x00 | near_input_rising_edge, pc_transition_of_interest |
| -217 | 3716 | -2 | 0 | 1 | 10 | 0x9206 | 0 | 0x00 | near_input_rising_edge |
| -217 | 3717 | -1 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | near_input_rising_edge, pc_transition_of_interest, sample_instruction_state_transition |
| -217 | 3718 | 0 | 1 | 1 | 6 | 0x2000 | 0 | 0x00 | near_input_rising_edge, sample_instruction_state_transition |
| -217 | 3719 | 1 | 1 | 0 | 7 | 0x2000 | 1 | 0x00 | near_input_rising_edge, pc_transition_of_interest, sample_register_changed |
| -217 | 3720 | 2 | 1 | 1 | 7 | 0x5000 | 1 | 0x00 | near_input_rising_edge |
| -217 | 3721 | 3 | 1 | 0 | 8 | 0x5000 | 1 | 0x01 | near_input_rising_edge, shift_register_changed |
| -217 | 4153 | 435 | 1 | 0 | 11 | 0x9206 | 1 | 0x01 | pc_transition_of_interest, sample_instruction_state_transition |
| -217 | 4154 | 436 | 1 | 1 | 11 | 0x2000 | 1 | 0x01 | sample_instruction_state_transition |
| -216 | 227 | -3492 | 0 | 0 | 2 | 0x30D6 | 0 | 0x00 | sample_instruction_state_transition |
| -216 | 228 | -3491 | 0 | 1 | 2 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -216 | 665 | -3054 | 0 | 0 | 6 | 0x30D7 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -216 | 666 | -3053 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -216 | 1101 | -2618 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -216 | 1102 | -2617 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -216 | 1537 | -2182 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -216 | 1538 | -2181 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -216 | 1973 | -1746 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -216 | 1974 | -1745 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -216 | 2409 | -1310 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -216 | 2410 | -1309 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -216 | 2845 | -874 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -216 | 2846 | -873 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -216 | 3281 | -438 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -216 | 3282 | -437 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -216 | 3716 | -3 | 0 | 1 | 10 | 0x9206 | 0 | 0x00 | near_input_rising_edge |
| -216 | 3717 | -2 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | near_input_rising_edge, pc_transition_of_interest, sample_instruction_state_transition |
| -216 | 3718 | -1 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | near_input_rising_edge, sample_instruction_state_transition |
| -216 | 3719 | 0 | 1 | 0 | 7 | 0x2000 | 1 | 0x00 | near_input_rising_edge, pc_transition_of_interest, sample_register_changed |
| -216 | 3720 | 1 | 1 | 1 | 7 | 0x5000 | 1 | 0x00 | near_input_rising_edge |
| -216 | 3721 | 2 | 1 | 0 | 8 | 0x5000 | 1 | 0x01 | near_input_rising_edge, shift_register_changed |
| -216 | 3722 | 3 | 1 | 1 | 8 | 0x30D5 | 1 | 0x01 | near_input_rising_edge |
| -216 | 4153 | 434 | 1 | 0 | 11 | 0x9206 | 1 | 0x01 | pc_transition_of_interest, sample_instruction_state_transition |
| -216 | 4154 | 435 | 1 | 1 | 11 | 0x2000 | 1 | 0x01 | sample_instruction_state_transition |
| -215 | 227 | -3493 | 0 | 0 | 2 | 0x30D6 | 0 | 0x00 | sample_instruction_state_transition |
| -215 | 228 | -3492 | 0 | 1 | 2 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -215 | 665 | -3055 | 0 | 0 | 6 | 0x30D7 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -215 | 666 | -3054 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -215 | 1101 | -2619 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -215 | 1102 | -2618 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -215 | 1537 | -2183 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -215 | 1538 | -2182 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -215 | 1973 | -1747 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -215 | 1974 | -1746 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -215 | 2409 | -1311 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -215 | 2410 | -1310 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -215 | 2845 | -875 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -215 | 2846 | -874 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -215 | 3281 | -439 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -215 | 3282 | -438 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -215 | 3717 | -3 | 0 | 0 | 6 | 0x9206 | 0 | 0x00 | near_input_rising_edge, pc_transition_of_interest, sample_instruction_state_transition |
| -215 | 3718 | -2 | 0 | 1 | 6 | 0x2000 | 0 | 0x00 | near_input_rising_edge, sample_instruction_state_transition |
| -215 | 3719 | -1 | 0 | 0 | 7 | 0x2000 | 0 | 0x00 | near_input_rising_edge, pc_transition_of_interest |
| -215 | 3720 | 0 | 1 | 1 | 7 | 0x5000 | 0 | 0x00 | near_input_rising_edge |
| -215 | 3721 | 1 | 1 | 0 | 8 | 0x5000 | 0 | 0x00 | near_input_rising_edge |
| -215 | 3722 | 2 | 1 | 1 | 8 | 0x30D5 | 0 | 0x00 | near_input_rising_edge |
| -215 | 3723 | 3 | 1 | 2 | 8 | 0x30D5 | 0 | 0x00 | near_input_rising_edge |
| -215 | 4153 | 433 | 1 | 0 | 11 | 0x9206 | 0 | 0x00 | pc_transition_of_interest, sample_instruction_state_transition |
| -215 | 4154 | 434 | 1 | 1 | 11 | 0x2000 | 0 | 0x00 | sample_instruction_state_transition |
| -215 | 4155 | 435 | 1 | 0 | 12 | 0x2000 | 1 | 0x00 | pc_transition_of_interest, sample_register_changed |

## Interpretation

The measured one-cycle transition tells us exactly where the current simulation changes classification. The cycle trace is needed to determine whether the input rising edge coincides with or passes the final data-bit sampling operation. A simultaneous edge/sample can depend on the model's cycle ordering; this experiment establishes the current simulation semantics, not physical silicon behavior.

Production RTL SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`
Detailed cycle CSV: `/home/rattan_0500/MORPH/traceforge/rtl_run/uart_boundary_diagnostic_v0_1_20261028T082705Z_22994/boundary_trace_cycles.csv`
JSON report: `/home/rattan_0500/MORPH/traceforge/reports/uart_boundary_diagnostic_v0_1_20261028T082705Z_22994.json`
Run directory: `/home/rattan_0500/MORPH/traceforge/rtl_run/uart_boundary_diagnostic_v0_1_20261028T082705Z_22994`
