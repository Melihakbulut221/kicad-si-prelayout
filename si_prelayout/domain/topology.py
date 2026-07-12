"""Domain models for SI pre-layout topologies."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class Corner(str, Enum):
    MIN = "min"
    TYP = "typ"
    MAX = "max"


class Material(BaseModel):
    name: str = "FR4"
    er: float = Field(4.2, gt=1.0, description="Relative permittivity")
    tand: float = Field(0.02, ge=0.0, description="Loss tangent")


class StackupLayer(BaseModel):
    name: str
    kind: Literal["signal", "plane", "dielectric"]
    thickness_m: float = Field(..., gt=0)
    material: str | None = None
    copper_weight_oz: float | None = None


class Stackup(BaseModel):
    materials: dict[str, Material] = Field(default_factory=lambda: {"FR4": Material()})
    layers: list[StackupLayer] = Field(default_factory=list)


class TraceRef(BaseModel):
    """Named transmission-line cross-section reference."""

    name: str
    style: Literal["microstrip", "stripline"] = "microstrip"
    z0_ohm: float | None = Field(None, gt=0, description="If set, used directly (MVP)")
    width_m: float | None = Field(None, gt=0)
    height_m: float | None = Field(None, gt=0)
    er: float = Field(4.2, gt=1.0)
    velocity_factor: float = Field(
        0.66,
        gt=0.1,
        lt=1.0,
        description="v / c0 for lossless delay; used when z0 is given directly",
    )
    lossy: bool = False
    r_dc_per_m: float = Field(5.0, ge=0.0)
    r_skin: float = Field(5e-5, ge=0.0, description="Ohm/m/√Hz skin term")
    tand: float = Field(0.02, ge=0.0)


class IbisRef(BaseModel):
    path: str | None = None
    model: str = "GENERIC_OUTPUT"
    corner: Corner = Corner.TYP


class ComponentBase(BaseModel):
    id: str


class IbisDriver(ComponentBase):
    type: Literal["ibis_driver"] = "ibis_driver"
    model: str = "GENERIC_OUTPUT"
    ibis: str | None = None
    corner: Corner = Corner.TYP
    # Idealized stimulus when full IBIS IV is unavailable
    v_high: float = 3.3
    v_low: float = 0.0
    r_series_ohm: float = 25.0
    edge_s: float = 0.2e-9
    delay_s: float = 1e-9
    pulse_width_s: float | None = 5e-9


class IbisReceiver(ComponentBase):
    type: Literal["ibis_receiver"] = "ibis_receiver"
    model: str = "GENERIC_INPUT"
    c_comp_f: float = 2e-12
    r_die_ohm: float = 1e6


class Tline(ComponentBase):
    type: Literal["tline"] = "tline"
    ref: str
    length_m: float = Field(..., gt=0)


class Resistor(ComponentBase):
    type: Literal["resistor"] = "resistor"
    ohms: float = Field(..., gt=0)
    to: Literal["gnd", "floating"] = "floating"


class Capacitor(ComponentBase):
    type: Literal["capacitor"] = "capacitor"
    farads: float = Field(..., gt=0)
    to: Literal["gnd"] = "gnd"


Component = Annotated[
    IbisDriver | IbisReceiver | Tline | Resistor | Capacitor,
    Field(discriminator="type"),
]


class NetConnection(BaseModel):
    """Connect component ports. Ports: .a / .b for 2-terminal, .out / .in for buffers."""

    connect: list[str] = Field(..., min_length=2)


class AnalyzeSpec(BaseModel):
    tstop_s: float = Field(20e-9, gt=0)
    dt_s: float = Field(5e-12, gt=0)
    probes: list[str] = Field(default_factory=list)
    checks: list[str] = Field(
        default_factory=lambda: ["overshoot", "undershoot", "monotonicity"]
    )


class Project(BaseModel):
    name: str = "untitled"
    description: str = ""
    stackup: Stackup = Field(default_factory=Stackup)
    traces: dict[str, TraceRef] = Field(default_factory=dict)
    ibis_files: dict[str, IbisRef] = Field(default_factory=dict)
    topology: list[Component]
    nets: list[NetConnection]
    analyze: AnalyzeSpec = Field(default_factory=AnalyzeSpec)

    @model_validator(mode="after")
    def _validate_refs(self) -> Project:
        ids = {c.id for c in self.topology}
        if len(ids) != len(self.topology):
            raise ValueError("Duplicate component ids in topology")
        for c in self.topology:
            if isinstance(c, Tline) and c.ref not in self.traces:
                raise ValueError(f"Tline {c.id} references unknown trace '{c.ref}'")
        return self
