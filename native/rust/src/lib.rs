//! Fast SI kernels: dense MNA solve + lossless MoC transmission lines.

use ndarray::{Array1, Array2};
use numpy::{PyArray1, PyReadonlyArray1, PyReadonlyArray2, ToPyArray};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// Dense linear solve G·v = i with partial-pivot Gaussian elimination.
fn solve_dense_rs(g: &Array2<f64>, rhs: &Array1<f64>) -> Result<Array1<f64>, String> {
    let n = rhs.len();
    if g.nrows() != n || g.ncols() != n {
        return Err(format!(
            "shape mismatch: G is {}x{}, i is {}",
            g.nrows(),
            g.ncols(),
            n
        ));
    }
    if n == 0 {
        return Ok(Array1::zeros(0));
    }

    let mut a = g.clone();
    let mut b = rhs.clone();

    for k in 0..n {
        // Pivot
        let mut piv = k;
        let mut best = a[[k, k]].abs();
        for r in (k + 1)..n {
            let v = a[[r, k]].abs();
            if v > best {
                best = v;
                piv = r;
            }
        }
        if best < 1e-18 {
            return Err("singular conductance matrix".into());
        }
        if piv != k {
            for c in k..n {
                let tmp = a[[k, c]];
                a[[k, c]] = a[[piv, c]];
                a[[piv, c]] = tmp;
            }
            let tmp = b[k];
            b[k] = b[piv];
            b[piv] = tmp;
        }

        let akk = a[[k, k]];
        for r in (k + 1)..n {
            let f = a[[r, k]] / akk;
            a[[r, k]] = 0.0;
            for c in (k + 1)..n {
                a[[r, c]] -= f * a[[k, c]];
            }
            b[r] -= f * b[k];
        }
    }

    let mut x = Array1::<f64>::zeros(n);
    for i in (0..n).rev() {
        let mut s = b[i];
        for j in (i + 1)..n {
            s -= a[[i, j]] * x[j];
        }
        x[i] = s / a[[i, i]];
    }
    Ok(x)
}

#[pyfunction]
fn solve_dense<'py>(
    py: Python<'py>,
    g: PyReadonlyArray2<'py, f64>,
    i_vec: PyReadonlyArray1<'py, f64>,
) -> PyResult<Bound<'py, PyArray1<f64>>> {
    let g = g.as_array().to_owned();
    let i_vec = i_vec.as_array().to_owned();
    let x = solve_dense_rs(&g, &i_vec).map_err(PyValueError::new_err)?;
    Ok(x.to_pyarray_bound(py))
}

/// Method-of-characteristics lossless line (Bergeron model).
#[pyclass]
struct LosslessLine {
    z0: f64,
    delay_steps: usize,
    hist_a: Vec<f64>,
    hist_b: Vec<f64>,
    k: usize,
    atten: f64,
}

#[pymethods]
impl LosslessLine {
    #[new]
    #[pyo3(signature = (z0, td_s, dt_s, atten=1.0))]
    fn new(z0: f64, td_s: f64, dt_s: f64, atten: f64) -> PyResult<Self> {
        if z0 <= 0.0 || dt_s <= 0.0 || td_s < 0.0 {
            return Err(PyValueError::new_err("invalid TL parameters"));
        }
        let delay_steps = ((td_s / dt_s).round() as usize).max(1);
        Ok(Self {
            z0,
            delay_steps,
            hist_a: vec![0.0; delay_steps + 2],
            hist_b: vec![0.0; delay_steps + 2],
            k: 0,
            atten: atten.clamp(0.0, 1.0),
        })
    }

    #[getter]
    fn z0(&self) -> f64 {
        self.z0
    }

    /// Return (E_a, E_b) delayed Thevenin waves.
    fn companion_sources(&self) -> (f64, f64) {
        let d = self.delay_steps;
        let k = self.k;
        let e_a = if k >= d { self.hist_b[k - d] } else { 0.0 };
        let e_b = if k >= d { self.hist_a[k - d] } else { 0.0 };
        (e_a, e_b)
    }

    fn commit(&mut self, v_a: f64, i_a_into: f64, v_b: f64, i_b_into: f64) {
        let wave_ab = self.atten * (v_a + self.z0 * i_a_into);
        let wave_ba = self.atten * (v_b + self.z0 * i_b_into);
        self.k += 1;
        if self.k >= self.hist_a.len() {
            self.hist_a.push(0.0);
            self.hist_b.push(0.0);
        }
        self.hist_a[self.k] = wave_ab;
        self.hist_b[self.k] = wave_ba;
    }
}

/// Linear IV table interpolation (IBIS-style).
#[pyfunction]
fn interp_iv(v_table: PyReadonlyArray1<'_, f64>, i_table: PyReadonlyArray1<'_, f64>, v: f64) -> f64 {
    let xv = v_table.as_array();
    let yv = i_table.as_array();
    let n = xv.len();
    if n == 0 {
        return 0.0;
    }
    if v <= xv[0] {
        return yv[0];
    }
    if v >= xv[n - 1] {
        return yv[n - 1];
    }
    // Binary search
    let mut lo = 0usize;
    let mut hi = n - 1;
    while hi - lo > 1 {
        let mid = (lo + hi) / 2;
        if xv[mid] <= v {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    let t = (v - xv[lo]) / (xv[hi] - xv[lo]).max(1e-30);
    yv[lo] + t * (yv[hi] - yv[lo])
}

/// Batch microstrip NEXT heuristic for many spacing values (UI sweeps).
#[pyfunction]
fn xtalk_next_batch<'py>(
    py: Python<'py>,
    spacings_m: PyReadonlyArray1<'_, f64>,
    height_m: f64,
) -> PyResult<Bound<'py, PyArray1<f64>>> {
    let s = spacings_m.as_array();
    let mut out = Array1::<f64>::zeros(s.len());
    for (i, &sp) in s.iter().enumerate() {
        let s_h = sp / height_m.max(1e-18);
        out[i] = (0.5 / (1.0 + s_h * s_h)).min(0.5);
    }
    Ok(out.to_pyarray_bound(py))
}

#[pymodule]
fn si_core_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", "0.3.0")?;
    m.add_function(wrap_pyfunction!(solve_dense, m)?)?;
    m.add_function(wrap_pyfunction!(interp_iv, m)?)?;
    m.add_function(wrap_pyfunction!(xtalk_next_batch, m)?)?;
    m.add_class::<LosslessLine>()?;
    m.add("backend", "rust")?;
    Ok(())
}
