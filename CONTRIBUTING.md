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

## Useful commands

```bash
si-prelayout analyze examples/ibis_series_terminated.si.yml
si-prelayout sweep examples/series_terminated.si.yml --series-r 10,33,47
si-prelayout xtalk --spacing-mil 6 --height-mil 4 --length-mil 2000
si-prelayout ui
```

## Roadmap pointers

See README. Highest-value next steps: vector-fitting lossy macromodels,
multi-conductor 2D RLGC, and a KiCad 9 IPC plugin shell.
