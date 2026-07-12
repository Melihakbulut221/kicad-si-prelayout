// Fast SI kernels in C++ (pybind11): dense MNA + MoC line.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <vector>

namespace py = pybind11;

static std::vector<double> solve_dense_cpp(const std::vector<double>& g_flat,
                                           ssize_t n,
                                           const std::vector<double>& rhs) {
  if (static_cast<ssize_t>(rhs.size()) != n) {
    throw std::runtime_error("rhs size mismatch");
  }
  if (static_cast<ssize_t>(g_flat.size()) != n * n) {
    throw std::runtime_error("G size mismatch");
  }
  std::vector<double> a = g_flat;
  std::vector<double> b = rhs;
  auto A = [&](ssize_t r, ssize_t c) -> double& { return a[r * n + c]; };

  for (ssize_t k = 0; k < n; ++k) {
    ssize_t piv = k;
    double best = std::abs(A(k, k));
    for (ssize_t r = k + 1; r < n; ++r) {
      double v = std::abs(A(r, k));
      if (v > best) {
        best = v;
        piv = r;
      }
    }
    if (best < 1e-18) {
      throw std::runtime_error("singular conductance matrix");
    }
    if (piv != k) {
      for (ssize_t c = k; c < n; ++c) std::swap(A(k, c), A(piv, c));
      std::swap(b[k], b[piv]);
    }
    double akk = A(k, k);
    for (ssize_t r = k + 1; r < n; ++r) {
      double f = A(r, k) / akk;
      A(r, k) = 0.0;
      for (ssize_t c = k + 1; c < n; ++c) A(r, c) -= f * A(k, c);
      b[r] -= f * b[k];
    }
  }

  std::vector<double> x(n, 0.0);
  for (ssize_t i = n - 1; i >= 0; --i) {
    double s = b[i];
    for (ssize_t j = i + 1; j < n; ++j) s -= A(i, j) * x[j];
    x[i] = s / A(i, i);
  }
  return x;
}

py::array_t<double> solve_dense(py::array_t<double, py::array::c_style | py::array::forcecast> g,
                                py::array_t<double, py::array::c_style | py::array::forcecast> i_vec) {
  auto gbuf = g.request();
  auto ibuf = i_vec.request();
  if (gbuf.ndim != 2 || ibuf.ndim != 1) {
    throw std::runtime_error("G must be 2D and i 1D");
  }
  ssize_t n = ibuf.shape[0];
  if (gbuf.shape[0] != n || gbuf.shape[1] != n) {
    throw std::runtime_error("shape mismatch");
  }
  double* gp = static_cast<double*>(gbuf.ptr);
  double* ip = static_cast<double*>(ibuf.ptr);
  std::vector<double> g_flat(gp, gp + n * n);
  std::vector<double> rhs(ip, ip + n);
  auto x = solve_dense_cpp(g_flat, n, rhs);
  auto out = py::array_t<double>(n);
  auto obuf = out.request();
  double* op = static_cast<double*>(obuf.ptr);
  std::copy(x.begin(), x.end(), op);
  return out;
}

class LosslessLine {
 public:
  LosslessLine(double z0, double td_s, double dt_s, double atten = 1.0)
      : z0_(z0), atten_(std::clamp(atten, 0.0, 1.0)), k_(0) {
    if (z0 <= 0.0 || dt_s <= 0.0 || td_s < 0.0) {
      throw std::runtime_error("invalid TL parameters");
    }
    delay_steps_ = static_cast<size_t>(std::max(1.0, std::round(td_s / dt_s)));
    hist_a_.assign(delay_steps_ + 2, 0.0);
    hist_b_.assign(delay_steps_ + 2, 0.0);
  }

  double z0() const { return z0_; }

  std::pair<double, double> companion_sources() const {
    double e_a = (k_ >= delay_steps_) ? hist_b_[k_ - delay_steps_] : 0.0;
    double e_b = (k_ >= delay_steps_) ? hist_a_[k_ - delay_steps_] : 0.0;
    return {e_a, e_b};
  }

  void commit(double v_a, double i_a_into, double v_b, double i_b_into) {
    double wave_ab = atten_ * (v_a + z0_ * i_a_into);
    double wave_ba = atten_ * (v_b + z0_ * i_b_into);
    ++k_;
    if (k_ >= hist_a_.size()) {
      hist_a_.push_back(0.0);
      hist_b_.push_back(0.0);
    }
    hist_a_[k_] = wave_ab;
    hist_b_[k_] = wave_ba;
  }

 private:
  double z0_;
  double atten_;
  size_t delay_steps_;
  std::vector<double> hist_a_;
  std::vector<double> hist_b_;
  size_t k_;
};

double interp_iv(py::array_t<double, py::array::c_style | py::array::forcecast> v_table,
                 py::array_t<double, py::array::c_style | py::array::forcecast> i_table,
                 double v) {
  auto vb = v_table.request();
  auto ib = i_table.request();
  ssize_t n = vb.shape[0];
  if (n == 0 || ib.shape[0] != n) return 0.0;
  double* xv = static_cast<double*>(vb.ptr);
  double* yv = static_cast<double*>(ib.ptr);
  if (v <= xv[0]) return yv[0];
  if (v >= xv[n - 1]) return yv[n - 1];
  ssize_t lo = 0, hi = n - 1;
  while (hi - lo > 1) {
    ssize_t mid = (lo + hi) / 2;
    if (xv[mid] <= v)
      lo = mid;
    else
      hi = mid;
  }
  double t = (v - xv[lo]) / std::max(xv[hi] - xv[lo], 1e-30);
  return yv[lo] + t * (yv[hi] - yv[lo]);
}

PYBIND11_MODULE(si_core_cpp, m) {
  m.doc() = "C++ SI kernels for si-prelayout (dense MNA + MoC)";
  m.attr("__version__") = "0.3.0";
  m.attr("backend") = "cpp";
  m.def("solve_dense", &solve_dense, "Dense G·v=i solve");
  m.def("interp_iv", &interp_iv, "Linear IV interpolation");
  py::class_<LosslessLine>(m, "LosslessLine")
      .def(py::init<double, double, double, double>(), py::arg("z0"), py::arg("td_s"),
           py::arg("dt_s"), py::arg("atten") = 1.0)
      .def_property_readonly("z0", &LosslessLine::z0)
      .def("companion_sources", &LosslessLine::companion_sources)
      .def("commit", &LosslessLine::commit);
}
