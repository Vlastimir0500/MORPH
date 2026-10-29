# TRACEFORGE â€” UART Aggregate Low-Run Boundary Sweep v0.2

- Status: **PASS**
- Payload: `0x00`; expected shift register: `0x00`
- Nominal contiguous low-run duration: 3924 cycles
- Sweep: -220â€¦-208 cycles, step 1; 14 cases
- Classifications: `{'correct_decode': 9, 'silent_misdecode': 5}`
- Minimized counterexample aggregate delta: -216 cycles; replay classification: `silent_misdecode`
- Saved vector exact match: **True**
- RTL/reference-model mismatches: 0
- Production RTL unchanged: **True**

## Classification intervals

| Classification | Delta start (cycles) | Delta end (cycles) | Cases |
|---|---:|---:|---:|
| silent_misdecode | -220 | -216 | 5 |
| correct_decode | -215 | -208 | 8 |
| correct_decode | 0 | 0 | 1 |

## One-cycle classification transitions

| From delta | From classification | To delta | To classification |
|---:|---|---:|---|
| -216 | silent_misdecode | -215 | correct_decode |

## Interpretation

For payload `0x00`, the start symbol and eight zero-valued data symbols create one continuous low-level interval on the input pin. This experiment therefore sweeps the observable duration of that interval rather than treating visually identical adjacent low symbols as independently observable edges.

The known minimized waveform is reconstructed from the sum of its first nine symbol offsets and must match the saved pin vector byte-for-byte. This fine sweep uses 1-cycle increments around the transition seen in v0.1; measured boundaries apply only to this firmware and timing model.

Production RTL SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`
JSON report: `/home/rattan_0500/MORPH/traceforge/reports/uart_aggregate_low_run_fine_sweep_v0_2_20261028T082415Z_22889.json`
Run directory: `/home/rattan_0500/MORPH/traceforge/rtl_run/uart_aggregate_low_run_fine_sweep_v0_2_20261028T082415Z_22889`
