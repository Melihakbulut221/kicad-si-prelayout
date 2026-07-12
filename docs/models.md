# Pre-layout SI architecture (LineSim-style)

## Goal

Open-source **pre-layout Signal Integrity** — user builds a topology
(driver → TL → termination → receiver), tool returns time-domain waveforms
and SI checks. KiCad integration and PI are later phases.

## Engines (v0.1)

| Block | Status |
|-------|--------|
| Topology YAML + Python API | Done |
| Closed-form Z0 preview | Done |
| Lossless TL (method of characteristics) | Done |
| Behavioral driver (PWL + Rs) | Done (IBIS IV/VT next) |
| Minimal IBIS model scanner | Done |
| Nodal transient (MNA + MoC) | Done |
| Overshoot / undershoot / monotonicity | Done |
| Streamlit UI what-if | Done |
| Lossy TL + vector fitting | Roadmap |
| Coupled / crosstalk | Roadmap |
| Full IBIS 2-EQ/2-WF | Roadmap |
| KiCad IPC plugin | Roadmap |

## Trust

Wrong SI is worse than no SI. Every model documents assumptions here and in code.
v0.1 is for education / early what-if — correlate before trusting silicon decisions.

## Validation targets

- Closed-form microstrip golden ranges
- ngspice cross-checks for simple R-TL-R nets
- IBIS Summit waveforms (once IV/VT lands)
