# kicad-si-prelayout

**Open-source pre-layout Signal Integrity** — a LineSim-style workflow for
building driver → transmission-line → termination topologies, simulating
reflections in the time domain, and reviewing SI checks.

> Status: **v0.1 alpha**. Lossless TL + behavioral driver MVP.
> Full IBIS IV/VT, lossy/causal lines, crosstalk, and KiCad IPC come next.

## Why

Commercial SI (HyperLynx, Sigrity, …) is expensive. Open-source has solvers
(openEMS, scikit-rf, atlc, ngspice) but not an integrated “draw a topology,
get a waveform” experience. This project starts at the highest-leverage
entry point: **pre-layout SI**.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[ui,dev]"

# CLI
si-prelayout analyze examples/series_terminated.si.yml --plot /tmp/si.png -r /tmp/si.md

# Friendly web UI
si-prelayout ui
```

Or: `streamlit run ui/app.py`

## What you get

- **YAML topology** projects (CI-friendly, reviewable)
- **Python API** (`load_project`, `run_simulation`)
- **CLI** with Rich tables + waveform plots
- **Streamlit Studio** — sliders for Rs / length / Z0 / edge, live waveforms
- **SI checks** — overshoot, undershoot, monotonicity (MVP)

## Example topology

See [`examples/series_terminated.si.yml`](examples/series_terminated.si.yml).

## Architecture (short)

1. Topology domain (Pydantic) ← YAML  
2. 2D closed-form Z0 (preview) → RLGC/MoM later  
3. Lossless TL via method of characteristics  
4. Small nodal transient solver  
5. Analysis / report / UI  

Details: [`docs/models.md`](docs/models.md)

## Roadmap

1. Full IBIS parser + 2-EQ/2-WF buffers  
2. Lossy lines (skin + Djordjevic–Sarkar) + vector fitting  
3. Coupled lines / crosstalk  
4. Corner & what-if sweeps + richer reports  
5. KiCad 9+ IPC plugin  

## License

MIT — see [LICENSE](LICENSE).
