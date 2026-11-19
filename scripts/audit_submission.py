#!/usr/bin/env python3
"""Offline structural, privacy, and README link audit for MORPH X submission.

This script does NOT prove ASIC functionality or replace GDS/precheck/formal CI.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
RTL_SHA = 'ebaad3f79ba71e2f958133a92d7d24a269396c161d89b4f51fda201d0895de98'
FW_SHA = '5a61cb59f5ccfabe6c10e92fc70b94a8bf3da34a136b76e1cc6e07adecb2ac5a'
REQUIRED_FILES = [
    'README.md', 'SUBMISSION.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
    'docs/AI_ASSISTANCE_DISCLOSURE.md', 'assets/readme/PROVENANCE.md',
    'rtl/morph_engine_v2.sv', 'protocols/v2_uart_rx_a6.hex',
    'compiler/morph_assembler_v2.py', 'compiler/morph_x_multireplay.py',
    'examples/morph_x_pulse_link_challenge.json',
    'tinytapeout-template-v2/src/project.v',
    'tinytapeout-template-v2/src/morph_engine.sv',
    'tinytapeout-template-v2/src/morph_x_trace_capture.sv',
    'tinytapeout-template-v2/info.yaml',
    'tinytapeout-template-v2/LICENSE',
    'formal/qualification/run.sh',
    'scripts/check_physical_signoff.py',
    'docs/MORPH_X_M6_LIMITATIONS.md',
    'docs/MORPH_X_PROTOCOL_ZERO_EVIDENCE_CHECKLIST.md',
    '.github/workflows/morph-engineering.yml',
    '.github/workflows/morph-formal-qualification.yml',
]
errors: list[str] = []
warnings: list[str] = []

def fail(message: str) -> None:
    errors.append(message)

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def tracked_files() -> list[Path]:
    paths = subprocess.check_output(
        ['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
        cwd=ROOT,
    ).split(b'\0')
    return [ROOT / os.fsdecode(p) for p in paths if p]

for relative in REQUIRED_FILES:
    if not (ROOT / relative).is_file():
        fail(f'Missing required file: {relative}')
if (ROOT / 'README.txt').exists():
    fail('Obsolete README.txt remains at root')

if (ROOT / 'rtl/morph_engine_v2.sv').exists():
    if sha256(ROOT / 'rtl/morph_engine_v2.sv') != RTL_SHA:
        fail('Protected production RTL SHA256 differs from frozen qualified baseline')
if (ROOT / 'protocols/v2_uart_rx_a6.hex').exists():
    if sha256(ROOT / 'protocols/v2_uart_rx_a6.hex') != FW_SHA:
        fail('Protected UART firmware SHA256 differs from frozen qualified baseline')
if (ROOT / 'rtl/morph_engine_v2.sv').exists() and (ROOT / 'tinytapeout-template-v2/src/morph_engine.sv').exists():
    if (ROOT / 'rtl/morph_engine_v2.sv').read_bytes() != (ROOT / 'tinytapeout-template-v2/src/morph_engine.sv').read_bytes():
        fail('Tiny Tapeout mirror is not byte-identical to production RTL')

info = ROOT / 'tinytapeout-template-v2/info.yaml'
if info.exists():
    content = info.read_text(encoding='utf-8', errors='replace')
    if not re.search(r'^\s*tiles:\s*["\']?8x4["\']?\s*(?:#.*)?$', content, re.MULTILINE):
        fail('Tiny Tapeout info.yaml is not configured for 8x4')
    if 'morph_x_trace_capture.sv' not in content:
        fail('Capture source not listed in Tiny Tapeout info.yaml')

# Full name in active release text; do not rewrite technical top-module IDs.
pattern = re.compile(r'rattandeep\s+singh', re.IGNORECASE)
for path in tracked_files():
    if not path.is_file() or path.is_symlink():
        continue
    blob = path.read_bytes()
    if b'\0' in blob:
        continue
    try:
        contents = blob.decode('utf-8')
    except UnicodeDecodeError:
        continue
    if pattern.search(contents):
        fail('Full personal name still visible: ' + str(path.relative_to(ROOT)))

# Validate relative paths from README and the judge guide. Ignore external URIs,
# pure anchors and file fragments. This does not verify remote URL availability.
markdown_link = re.compile(r'!?\[[^\]]*\]\(([^)]+)\)')
html_link = re.compile(r'\b(?:src|href)=["\']([^"\']+)["\']')
for doc in (ROOT / 'README.md', ROOT / 'SUBMISSION.md'):
    if not doc.exists():
        continue
    content = doc.read_text(encoding='utf-8')
    for target in markdown_link.findall(content) + html_link.findall(content):
        target = target.split('#', 1)[0].split('?', 1)[0].strip()
        if not target or re.match(r'^(?:https?:|mailto:|data:|//)', target):
            continue
        target = unquote(target).replace('\\', '/')
        candidate = (doc.parent / target).resolve()
        try:
            candidate.relative_to(ROOT)
        except ValueError:
            fail(f'{doc.name}: link leaves repository: {target}')
            continue
        if not candidate.exists():
            fail(f'{doc.name}: broken relative link: {target}')

if (ROOT / '.github/workflows/morph-engineering.yml').exists():
    work = (ROOT / '.github/workflows/morph-engineering.yml').read_text()
    for token in ['tt-gds-action', 'precheck', 'gate-level-test', 'physical-signoff']:
        if token not in work:
            fail('Engineering workflow missing key: ' + token)

readme = ROOT / 'README.md'
if readme.exists():
    s = readme.read_text(encoding='utf-8')
    if 'branch=feat%2Fmorph-x' in s:
        fail('README CI badge still targets old feat/morph-x instead of release')
    if 'SUBMISSION.md' not in s:
        warnings.append('README does not link to judge-facing SUBMISSION.md')

print(f'Checked {len(REQUIRED_FILES)} required files and {len(tracked_files())} tracked/untracked visible paths.')
if warnings:
    for item in warnings:
        print('WARNING:', item)
if errors:
    for item in errors:
        print('FAIL:', item, file=sys.stderr)
    print(f'AUDIT FAILED: {len(errors)} issue(s)', file=sys.stderr)
    sys.exit(1)
print('AUDIT PASSED: file structure, protected hashes, 8x4, privacy, and relative links.')
print('NOTICE: This is not a replacement for exact-commit Tiny Tapeout GDS/precheck and formal verification.')
