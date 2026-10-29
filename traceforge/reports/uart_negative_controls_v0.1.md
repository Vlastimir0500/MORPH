# TRACEFORGE â€” UART Negative Controls v0.1

- Status: **PASS**
- Scenarios passed: 7/7
- Production RTL SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`
- Existing source evidence files modified: **No**
- Production RTL modified: **No**

## Results

| Scenario | Expected | Observed | Test | Detection |
|---|---|---|---|---|
| clean_baseline | PASS | PASS | PASS | none |
| misclassify_nominal_uart_case | REJECT | REJECTED | PASS | 1 in-envelope cases violate the UART evidence contract; timing audit pass count disagrees with the matrix; one or more nominal-period UART cases fail |
| inject_rtl_reference_mismatch | REJECT | REJECTED | PASS | 1 in-envelope cases violate the UART evidence contract; timing audit pass count disagrees with the matrix; one or more nominal-period UART cases fail |
| erase_counterexample_reproduction | REJECT | REJECTED | PASS | known silent UART misdecode was not reproduced |
| corrupt_in_envelope_pass_count | REJECT | REJECTED | PASS | timing audit pass count disagrees with the matrix |
| stale_production_rtl_hash | REJECT | REJECTED | PASS | timing matrix production RTL hash is stale |
| mark_evidence_audit_failed | REJECT | REJECTED | PASS | UART evidence-contract audit status is not PASS |

These are checker-level negative controls over temporary in-memory evidence mutations. They do not alter the source reports and do not constitute a fix for the known UART receiver limitation.
