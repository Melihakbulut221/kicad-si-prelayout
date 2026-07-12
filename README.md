# kicad-si-prelayout

**Open-source pre-layout Signal Integrity** — LineSim-style topologies,
time-domain waveforms, IBIS drivers, and what-if sweeps.

> Status: **v0.3** — Rust + C++ native solvers (MoC / dense MNA), Streamlit Studio UI.

## Architecture

| Layer | Language | Role |
|-------|----------|------|
| Solvers | **Rust** (`si_core_rust`) + **C++** (`si_core_cpp`) | Dense MNA, MoC TL, IV interp |
| Orchestration | Python | Topology, IBIS 2-EQ/2-WF, reports, CLI |
| UI | **Streamlit** | Friendly what-if studio (knobs + plots + checks) |

Python always works alone; natives accelerate the hot path when built.
Backend preference: **Rust → C++ → Python**.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[ui,dev,native]"

# Optional: build fast solvers (needs rustc + g++)
bash scripts/build_native.sh
si-prelayout backend          # should say rust or cpp

si-prelayout analyze examples/series_terminated.si.yml --plot /tmp/si.png
si-prelayout analyze examples/ibis_series_terminated.si.yml -j /tmp/si.json
si-prelayout sweep examples/series_terminated.si.yml --series-r 10,22,33,47
si-prelayout ui               # Streamlit Studio
```

## CLI helpers

```bash
si-prelayout z0 --width-mil 6 --height-mil 4
si-prelayout zdiff --width-mil 5 --height-mil 4 --gap-mil 5
si-prelayout budget --skew-ps 10
si-prelayout xtalk --spacing-mil 6 --height-mil 4 --length-mil 2000
```

## Examples

| File | Description |
|------|-------------|
| `examples/series_terminated.si.yml` | PWL driver + series R |
| `examples/parallel_terminated.si.yml` | Matched far-end |
| `examples/ibis_series_terminated.si.yml` | IBIS + lossy TL |
| `examples/buffers/generic_25ohm.ibs` | Synthetic IBIS |

## Native kernels

```
native/rust/   # PyO3 — si_core_rust
native/cpp/    # pybind11 — si_core_cpp
```

See [`docs/models.md`](docs/models.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Roadmap

- Wire full transient loop into Rust (less Python per timestep)
- Gustavsen VF + passivity
- Coupled MoM RLGC
- KiCad 9+ IPC plugin

## License

MIT — see [LICENSE](LICENSE).
