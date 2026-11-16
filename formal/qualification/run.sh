#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
command -v yosys >/dev/null
command -v sby >/dev/null
command -v yosys-abc >/dev/null
printf 'Yosys: '
yosys -V
printf 'Formal proof 1/2: top-level output gating\n'
mkdir -p build/formal
sby -f -d build/formal/gating formal/qualification/gating.sby
printf 'Formal proof 2/2: fault forces pin release after reset\n'
sby -f -d build/formal/fault formal/qualification/fault.sby
for property in gating fault; do
    status="$(awk 'NR==1 {print $1}' "build/formal/$property/status")"
    if [[ "$status" != 'PASS' ]]; then
        printf '%s formal status: %s\n' "$property" "$status" >&2
        exit 1
    fi
    printf '%s proof: %s\n' "$property" "$status"
done
