# kicad-si-prelayout

**Open-source pre-layout Signal Integrity** — a LineSim-style workflow for
building driver → transmission-line → termination topologies, simulating
reflections in the time domain, and reviewing SI checks.

> Status: **v0.2 alpha** — IBIS 2-EQ/2-WF drivers, lossy-line approx, what-if sweeps.

## Why

Commercial SI (HyperLynx, Sigrity, …) is expensive. Open-source has solvers
(openEMS, scikit-rf, atlc, ngspice) but not an integrated “draw a topology,
get a waveform” experience. This project starts at **pre-layout SI**.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[ui,dev]"

# Behavioral driver demo
si-prelayout analyze examples/series_terminated.si.yml --plot /tmp/si.png

# IBIS-driven demo (synthetic model)
si-prelayout analyze examples/ibis_series_terminated.si.yml -r /tmp/si.md

# What-if sweep
si-prelayout sweep examples/series_terminated.si.yml --series-r 10,22,33,47

# Friendly web UI
si-prelayout ui
```

## What you get

- **YAML topology** projects (CI-friendly)
- **Python API** (`load_project`, `run_simulation`)
- **CLI** with Rich tables, plots, and sweeps
- **Streamlit Studio** — Rs / length / Z0 / edge knobs
- **IBIS** subset parser + 2-EQ/2-WF switching coefficients
- **Lossy TL** first-order attenuation (skin + Djordjevic–Sarkar helpers)
- **SI checks** — overshoot, undershoot, monotonicity

## Examples

| File | Description |
|------|-------------|
| `examples/series_terminated.si.yml` | PWL driver + series R + open-ish RX |
| `examples/parallel_terminated.si.yml` | Matched far-end |
| `examples/ibis_series_terminated.si.yml` | IBIS GENERIC_OUTPUT + lossy TL |
| `examples/buffers/generic_25ohm.ibs` | Synthetic self-consistent IBIS |

## Architecture

1. Topology domain (Pydantic) ← YAML  
2. IBIS IV/VT → Ku/Kd (2-EQ/2-WF)  
3. MoC TL (± loss attenuation)  
4. Nodal transient (Newton for IBIS)  
5. Checks / sweeps / UI  

Details: [`docs/models.md`](docs/models.md)

## Roadmap

1. ~~IBIS parser + 2-EQ/2-WF~~  
2. Vector fitting lossy macromodels  
3. Coupled lines / crosstalk  
4. Richer corner reports + eye metrics  
5. KiCad 9+ IPC plugin  

## License

MIT — see [LICENSE](LICENSE).
