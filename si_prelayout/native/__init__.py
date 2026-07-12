"""Select and expose native solver backends (Rust / C++ / Python)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

_BACKEND_NAME = "python"
_mod: Any = None


class LosslessLineProto(Protocol):
    z0: float

    def companion_sources(self) -> tuple[float, float]: ...

    def commit(self, v_a: float, i_a: float, v_b: float, i_b: float) -> None: ...


def _try_import() -> None:
    global _BACKEND_NAME, _mod
    # Prefer Rust, then C++, then pure Python
    for name, label in (("si_core_rust", "rust"), ("si_core_cpp", "cpp")):
        try:
            _mod = __import__(name)
            _BACKEND_NAME = label
            return
        except ImportError:
            continue
    _mod = None
    _BACKEND_NAME = "python"


_try_import()


def backend_name() -> str:
    return _BACKEND_NAME


def reload_backend() -> str:
    _try_import()
    return _BACKEND_NAME


def solve_dense(g: np.ndarray, i_vec: np.ndarray) -> np.ndarray:
    """Solve G·v = i. Uses native backend when available."""
    g = np.ascontiguousarray(g, dtype=np.float64)
    i_vec = np.ascontiguousarray(i_vec, dtype=np.float64)
    if _mod is not None:
        return np.asarray(_mod.solve_dense(g, i_vec), dtype=np.float64)
    return np.linalg.solve(g, i_vec)


def make_lossless_line(
    z0: float, td_s: float, dt_s: float, atten: float = 1.0
) -> LosslessLineProto:
    if _mod is not None and hasattr(_mod, "LosslessLine"):
        return _mod.LosslessLine(z0, td_s, dt_s, atten)
    from si_prelayout.tline.lossless import LosslessLine as PyLine

    line = PyLine(z0=z0, td_s=td_s, dt_s=dt_s)
    # emulate atten via monkeypatch on commit
    if atten < 1.0 - 1e-15:
        orig = line.commit

        def _commit(v_a, i_a, v_b, i_b, _orig=orig, _a=atten):
            _orig(v_a, i_a, v_b, i_b)
            line._hist_a[line._k] *= _a
            line._hist_b[line._k] *= _a

        line.commit = _commit  # type: ignore[method-assign]
    return line


def interp_iv(v_table: np.ndarray, i_table: np.ndarray, v: float) -> float:
    if _mod is not None and hasattr(_mod, "interp_iv"):
        return float(
            _mod.interp_iv(
                np.ascontiguousarray(v_table, dtype=np.float64),
                np.ascontiguousarray(i_table, dtype=np.float64),
                float(v),
            )
        )
    return float(np.interp(v, v_table, i_table))


@dataclass
class BackendInfo:
    name: str
    module: str | None
    version: str | None


def info() -> BackendInfo:
    if _mod is None:
        return BackendInfo(name="python", module=None, version=None)
    return BackendInfo(
        name=_BACKEND_NAME,
        module=getattr(_mod, "__name__", None),
        version=getattr(_mod, "__version__", None),
    )
