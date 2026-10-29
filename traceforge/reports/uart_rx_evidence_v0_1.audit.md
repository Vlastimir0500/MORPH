# TRACEFORGE Contract Audit: uart_rx_evidence_v0_1

- Status: **PASS**
- Checks passed: 12/12

| Check | Result | Details |
|---|---|---|
| production_rtl_matches_evidence_revision | PASS | SHA-256 actual=6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552 |
| matrix_records_same_production_rtl | PASS | expected=6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552; actual=6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552 |
| payload_timing_matrix_has_zero_rtl_model_mismatches | PASS | expected=0; actual=0 |
| all_nominal_payload_frames_decode_correctly | PASS | 8 matched cases; 0 assertion failures |
| common_measured_period_envelope_passes | PASS | 384 matched cases; 0 assertion failures |
| jitter_stress_case_count_is_reproducible | PASS | expected=600; actual=600 |
| jitter_stress_has_zero_rtl_model_mismatches | PASS | expected=0; actual=0 |
| jitter_stress_result_counts_match_recorded_run | PASS | expected={'correct_decode': 570, 'error_flagged': 5, 'silent_misdecode': 25}; actual={'correct_decode': 570, 'error_flagged': 5, 'silent_misdecode': 25} |
| minimized_counterexample_replays_exactly | PASS | expected=True; actual=True |
| minimized_counterexample_matches_reference_model | PASS | expected=True; actual=True |
| minimized_counterexample_is_a_silent_wrong_byte | PASS | expected=True; actual=True |
| counterexample_observed_byte_is_reproducible | PASS | expected=0x01; actual=0x01 |
