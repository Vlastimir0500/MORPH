# AI-assisted development disclosure

MORPH X used AI assistants for portions of code drafting, review, documentation, research organization and visualization. The repository's engineering evidence is provided as executable tests, reproducible artifacts and GitHub Actions results rather than relying on generated prose as proof.

The README hero is concept artwork; block/ISA diagrams and animated waveforms explain the architecture; KLayout images come from an inspected GDS view. See [visual asset provenance](../assets/readme/PROVENANCE.md).

AI assistance does not imply independent hardware validation. Formal checks prove only the explicitly specified safety properties; software model checks, RTL simulation, gate-level simulation, physical-design precheck and manufactured-silicon behavior are separate evidence categories.

The project maintainer should expand this statement if any tool or assistance details are omitted. Jane Street explicitly permits AI tools but requests disclosure in the write-up.
