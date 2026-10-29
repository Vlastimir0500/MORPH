MORPH temporal contract verifier add-on

Install from WSL by copying this archive to /mnt/c/Users/annoy/Downloads and running:
  cd ~/MORPH
  unzip -o /mnt/c/Users/annoy/Downloads/morph-contract-addon.zip -d .
  export PATH=/home/rattan_0500/.venvs/morph-test/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
  ~/.venvs/morph-test/bin/python compiler/morph_contract.py protocols/edge_timed_release.contract.json
  ~/.venvs/morph-test/bin/python -m pytest -q sim

This tool statically checks the current assembled program against a JSON contract:
program word budget, required mnemonics, exact DRIVE sequence, maximum WAIT, and backward branch presence.
It writes a JSON report with compiled words, disassembly, source SHA-256, and individual checks.
It does not yet prove cycle-level timing correctness or formal properties; this is the initial contract-validation milestone.
