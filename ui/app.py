"""SI Pre-Layout Studio — friendly Streamlit UI."""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
import yaml

from si_prelayout.api import load_project, run_simulation
from si_prelayout.domain.topology import IbisDriver, Project, Resistor, Tline

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"

st.set_page_config(
    page_title="SI Pre-Layout Studio",
    page_icon="📡",
    layout="wide",
)

st.title("SI Pre-Layout Studio")
st.caption(
    "Open-source LineSim-style pre-layout SI — edit topology knobs, "
    "simulate reflections, review checks."
)

example_files = sorted(EXAMPLES.glob("*.si.yml")) if EXAMPLES.exists() else []
example_names = [p.name for p in example_files]

with st.sidebar:
    st.header("Project")
    choice = st.selectbox("Example", example_names or ["(none)"])
    uploaded = st.file_uploader("Or upload .si.yml", type=["yml", "yaml"])

    st.divider()
    st.header("What-if knobs")
    rs = st.slider("Series R (Ω)", 0.0, 100.0, 33.0, 1.0)
    length_mm = st.slider("Main TL length (mm)", 5.0, 300.0, 80.0, 5.0)
    z0 = st.slider("Trace Z0 (Ω)", 30.0, 100.0, 50.0, 1.0)
    edge_ns = st.slider("Driver edge (ns)", 0.05, 2.0, 0.2, 0.05)
    run_btn = st.button("Run simulation", type="primary", use_container_width=True)


def _load_base() -> Project:
    if uploaded is not None:
        data = yaml.safe_load(uploaded.getvalue())
        return Project.model_validate(data)
    if example_files:
        idx = example_names.index(choice)
        return load_project(example_files[idx])
    raise FileNotFoundError("No example projects found under examples/")


def _apply_knobs(project: Project) -> Project:
    """Mutate a copy via dump/validate for slider overrides."""
    data = project.model_dump(mode="json")
    for tr in data.get("traces", {}).values():
        tr["z0_ohm"] = z0
    for comp in data["topology"]:
        if comp["type"] == "resistor" and comp.get("to") != "gnd":
            # first floating resistor = series termination
            if abs(comp["ohms"] - 33.0) < 1e-6 or comp["id"].lower().startswith("rser"):
                comp["ohms"] = rs
        if comp["type"] == "tline" and comp["id"] in {"T1", "t1", "MAIN"}:
            comp["length_m"] = length_mm * 1e-3
        if comp["type"] == "ibis_driver":
            comp["edge_s"] = edge_ns * 1e-9
            # also update series R inside driver if no external series R intent
    # Prefer updating first floating resistor and first long-ish tline
    floating_r = [
        c for c in data["topology"] if c["type"] == "resistor" and c.get("to") != "gnd"
    ]
    if floating_r:
        floating_r[0]["ohms"] = rs
    tlines = [c for c in data["topology"] if c["type"] == "tline"]
    if tlines:
        tlines[0]["length_m"] = length_mm * 1e-3
    drivers = [c for c in data["topology"] if c["type"] == "ibis_driver"]
    if drivers:
        drivers[0]["edge_s"] = edge_ns * 1e-9
    return Project.model_validate(data)


if "result" not in st.session_state:
    st.session_state.result = None
    st.session_state.project = None

if run_btn or st.session_state.result is None:
    try:
        base = _load_base()
        project = _apply_knobs(base)
        with st.spinner("Simulating…"):
            result = run_simulation(project)
        st.session_state.result = result
        st.session_state.project = project
    except Exception as exc:  # noqa: BLE001 — show in UI
        st.error(f"Simulation failed: {exc}")
        st.stop()

result = st.session_state.result
project = st.session_state.project

col_plot, col_checks = st.columns([2.2, 1])

with col_plot:
    st.subheader("Waveforms")
    fig = go.Figure()
    for wf in result.waveforms:
        fig.add_trace(
            go.Scatter(
                x=wf.t_s * 1e9,
                y=wf.v_v,
                mode="lines",
                name=wf.name,
            )
        )
    fig.update_layout(
        xaxis_title="Time (ns)",
        yaxis_title="Voltage (V)",
        margin=dict(l=40, r=20, t=30, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=420,
        template="plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)

with col_checks:
    st.subheader("SI checks")
    for c in result.checks:
        icon = "✅" if c.passed else "❌"
        st.markdown(f"{icon} **{c.name}**")
        st.caption(c.message)
    st.divider()
    st.markdown(f"**Project:** {project.name}")
    st.caption(project.description or "—")
    n_tl = sum(1 for c in project.topology if isinstance(c, Tline))
    n_r = sum(1 for c in project.topology if isinstance(c, Resistor))
    n_drv = sum(1 for c in project.topology if isinstance(c, IbisDriver))
    st.write(f"Drivers: {n_drv} · TLines: {n_tl} · Resistors: {n_r}")

with st.expander("Topology YAML (effective)"):
    st.code(yaml.safe_dump(project.model_dump(mode="json"), sort_keys=False), language="yaml")

st.info(
    "Engine: MoC transmission lines (± loss attenuation) + PWL or IBIS 2-EQ/2-WF drivers. "
    "Try `ibis_series_terminated.si.yml`. Full VF macromodels and coupled MoM are on the roadmap."
)
