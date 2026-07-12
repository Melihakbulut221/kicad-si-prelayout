from pybind11.setup_helpers import Pybind11Extension, build_ext
from setuptools import setup

ext = Pybind11Extension(
    "si_core_cpp",
    ["native/cpp/src/si_core_cpp.cpp"],
    cxx_std=17,
)

setup(
    name="si-core-cpp",
    version="0.3.0",
    ext_modules=[ext],
    cmdclass={"build_ext": build_ext},
    zip_safe=False,
)
