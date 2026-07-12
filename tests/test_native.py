"""Native backend smoke tests (skip if not built)."""

import numpy as np
import pytest

from si_prelayout.native import backend_name, info, make_lossless_line, reload_backend, solve_dense


def test_backend_loads():
    name = reload_backend()
    assert name in {"rust", "cpp", "python"}
    meta = info()
    assert meta.name == name


def test_solve_dense_identity():
    g = np.eye(4) * 5.0
    i = np.arange(1, 5, dtype=float)
    v = solve_dense(g, i)
    np.testing.assert_allclose(v, i / 5.0, rtol=1e-9)


def test_moc_line_roundtrip():
    line = make_lossless_line(50.0, td_s=1e-9, dt_s=1e-11, atten=1.0)
    assert line.z0 == 50.0
    e_a, e_b = line.companion_sources()
    assert e_a == 0.0 and e_b == 0.0
    line.commit(1.0, 0.0, 0.5, 0.0)


@pytest.mark.skipif(backend_name() == "python", reason="native backend not built")
def test_native_not_python():
    assert backend_name() in {"rust", "cpp"}
