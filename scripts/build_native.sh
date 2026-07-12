#!/usr/bin/env bash
# Build Rust (PyO3) and C++ (pybind11) native SI kernels into the active venv.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PATH="${HOME}/.cargo/bin:${PATH}"

echo "==> Building Rust si_core_rust (maturin)"
python -m pip install -q maturin numpy
maturin develop --release --manifest-path native/rust/Cargo.toml

echo "==> Building C++ si_core_cpp (pybind11)"
python -m pip install -q pybind11 setuptools wheel
python native/cpp/setup.py build_ext --inplace
# Move .so next to import path / into site-packages via copy to project root
SO=$(ls -1 si_core_cpp*.so 2>/dev/null | head -1 || true)
if [[ -n "${SO}" ]]; then
  echo "    built ${SO}"
  # also copy into venv site-packages for clean imports
  SP=$(python -c "import site; print(site.getsitepackages()[0])")
  cp -f "${SO}" "${SP}/"
  echo "    installed to ${SP}/${SO}"
fi

python - <<'PY'
from si_prelayout.native import info, reload_backend
print("backend after build:", reload_backend(), info())
PY

echo "Done."
