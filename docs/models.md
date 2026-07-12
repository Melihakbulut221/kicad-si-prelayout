# Pre-layout SI architecture (LineSim-style)

## Goal

Open-source **pre-layout Signal Integrity** — user builds a topology
(driver → TL → termination → receiver), tool returns time-domain waveforms
and SI checks. KiCad integration and PI are later phases.

## Engines (v0.2)

| Block | Status |
|-------|--------|
| Topology YAML + Python API | Done |
| Closed-form Z0 preview | Done |
| Lossless TL (method of characteristics) | Done |
| Lossy TL approx (α(f)·ℓ attenuation + Rseries) | Done (MVP) |
| Djordjevic–Sarkar + skin helpers | Done |
| Behavioral PWL driver | Done |
| IBIS parser (IV/VT/C_comp/Ramp) | Done |
| 2-EQ/2-WF Ku/Kd extraction | Done |
| Nonlinear IBIS buffer in MNA | Done |
| What-if sweeps (Rseries, length, corners) | Done |
| Streamlit Studio | Done |
| Vector fitting macromodels | Roadmap |
| Coupled / crosstalk | Roadmap |
| KiCad IPC plugin | Roadmap |

## IBIS notes

- Currents follow IBIS **into-buffer** sign convention.
- Pullup table voltage is **Vcc − Vpad**.
- Ku/Kd are extracted offline from ≥2 rising and ≥2 falling VT waveforms.
- Synthetic model: `examples/buffers/generic_25ohm.ibs` (self-consistent, not silicon).

## Loss notes

- Edge frequency fe ≈ 0.35/tr sets α; traveling waves scaled by e^{-αℓ}.
- This is a teaching / early what-if model — not VF-quality.

## Trust

Wrong SI is worse than no SI. Correlate before trusting silicon decisions.
