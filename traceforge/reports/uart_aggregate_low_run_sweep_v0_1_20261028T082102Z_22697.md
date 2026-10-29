# TRACEFORGE â€” UART Aggregate Low-Run Sweep v0.1

- Status: **PASS**
- Payload: `0x00`; expected shift register: `0x00`
- Nominal contiguous low-run duration: 3924 cycles
- Sweep: -320â€¦+80 cycles, step 4; 101 cases
- Classifications: `{'correct_decode': 74, 'silent_misdecode': 27}`
- Minimized counterexample aggregate delta: -216 cycles; replay classification: `silent_misdecode`
- Saved vector exact match: **True**
- RTL/reference-model mismatches: 0
- Production RTL unchanged: **True**

## Classification intervals

| Classification | Delta start (cycles) | Delta end (cycles) | Cases |
|---|---:|---:|---:|
| silent_misdecode | -320 | -216 | 27 |
| correct_decode | -212 | 80 | 74 |

## Interpretation

For payload `0x00`, the start symbol and eight zero-valued data symbols create one continuous low-level interval on the input pin. This experiment therefore sweeps the observable duration of that interval rather than treating visually identical adjacent low symbols as independently observable edges.

The known minimized waveform is reconstructed from the sum of its first nine symbol offsets and must match the saved pin vector byte-for-byte. The grid is finite and 4-cycle spaced; fine-grained boundary behavior requires a follow-up sweep around any transitions.

Production RTL SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`
JSON report: `/home/rattan_0500/MORPH/traceforge/reports/uart_aggregate_low_run_sweep_v0_1_20261028T082102Z_22697.json`
Run directory: `/home/rattan_0500/MORPH/traceforge/rtl_run/uart_aggregate_low_run_sweep_v0_1_20261028T082102Z_22697`
