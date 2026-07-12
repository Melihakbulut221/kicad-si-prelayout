# Contributing

Thanks for helping build open-source pre-layout SI.

## Dev setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[ui,dev]"
pytest -q
```

## Project norms

- Keep the **core solver** independent of KiCad (headless YAML + API first).
- Document model assumptions in `docs/models.md` — wrong SI is worse than none.
- Prefer golden / heuristic tests over silent numerical changes.
- Synthetic IBIS: regenerate with `python scripts/generate_generic_ibis.py`.

## Native solvers (Rust / C++)

```bash
# Requires: rustup toolchain + g++ + Python venv
pip install -e ".[native]"
bash scripts/build_native.sh
si-prelayout backend   # expect: rust (preferred) or cpp
```

- Rust crate: `native/rust` → module `si_core_rust`
- C++ module: `native/cpp` → module `si_core_cpp`
- Python selects backend in `si_prelayout/native/__init__.py`

Hot path today: dense `G·v=i` and MoC lossless/attenuated lines.

## Roadmap pointers

See README. Highest-value next steps: vector-fitting lossy macromodels,
multi-conductor 2D RLGC, and a KiCad 9 IPC plugin shell.
