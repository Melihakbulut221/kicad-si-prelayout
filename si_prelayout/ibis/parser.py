"""IBIS file parser (subset): IV tables, VT waveforms, C_comp, Ramp, Voltage Range."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import re

import numpy as np

from si_prelayout.domain.topology import Corner


class WaveKind(str, Enum):
    RISING = "rising"
    FALLING = "falling"


@dataclass
class IvTable:
    """Voltage (V) → current (A). Pullup voltages are Vcc-referenced as in IBIS."""

    v: np.ndarray
    i_typ: np.ndarray
    i_min: np.ndarray | None = None
    i_max: np.ndarray | None = None

    def current(self, voltage: float | np.ndarray, corner: Corner = Corner.TYP) -> np.ndarray:
        if corner == Corner.MIN and self.i_min is not None:
            i = self.i_min
        elif corner == Corner.MAX and self.i_max is not None:
            i = self.i_max
        else:
            i = self.i_typ
        return np.interp(voltage, self.v, i)


@dataclass
class VtWaveform:
    kind: WaveKind
    r_fixture: float
    v_fixture: float
    v_fixture_min: float | None = None
    v_fixture_max: float | None = None
    t: np.ndarray = field(default_factory=lambda: np.array([]))
    v_typ: np.ndarray = field(default_factory=lambda: np.array([]))
    v_min: np.ndarray | None = None
    v_max: np.ndarray | None = None

    def voltage(self, t: float | np.ndarray, corner: Corner = Corner.TYP) -> np.ndarray:
        if corner == Corner.MIN and self.v_min is not None:
            v = self.v_min
        elif corner == Corner.MAX and self.v_max is not None:
            v = self.v_max
        else:
            v = self.v_typ
        return np.interp(t, self.t, v)


@dataclass
class Ramp:
    dv_dt_r_typ: float = 1e9  # V/s rising
    dv_dt_f_typ: float = 1e9
    dv_dt_r_min: float | None = None
    dv_dt_f_min: float | None = None
    dv_dt_r_max: float | None = None
    dv_dt_f_max: float | None = None
    r_load: float = 50.0


@dataclass
class IbisModel:
    name: str
    model_type: str = "Output"
    polarity: str = "Non-Inverting"
    vcc: float = 3.3
    c_comp: float = 0.0
    c_comp_min: float | None = None
    c_comp_max: float | None = None
    voltage_range: tuple[float, float, float] | None = None  # typ,min,max
    pullup: IvTable | None = None
    pulldown: IvTable | None = None
    power_clamp: IvTable | None = None
    gnd_clamp: IvTable | None = None
    rising: list[VtWaveform] = field(default_factory=list)
    falling: list[VtWaveform] = field(default_factory=list)
    ramp: Ramp | None = None
    source_path: str = ""

    def c_comp_for(self, corner: Corner) -> float:
        if corner == Corner.MIN and self.c_comp_min is not None:
            return self.c_comp_min
        if corner == Corner.MAX and self.c_comp_max is not None:
            return self.c_comp_max
        return self.c_comp

    def vcc_for(self, corner: Corner) -> float:
        if self.voltage_range is None:
            return self.vcc
        typ, vmin, vmax = self.voltage_range
        if corner == Corner.MIN:
            return vmin
        if corner == Corner.MAX:
            return vmax
        return typ


@dataclass
class IbisFile:
    path: str
    ibis_version: str = ""
    file_name: str = ""
    models: dict[str, IbisModel] = field(default_factory=dict)

    def get(self, name: str) -> IbisModel:
        if name not in self.models:
            raise KeyError(f"IBIS model '{name}' not found in {self.path}")
        return self.models[name]


_NUM = re.compile(
    r"([+-]?(?:\d+\.\d*|\d*\.\d+|\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Z]*)"
)


def _parse_number(token: str) -> float:
    token = token.strip().rstrip(",")
    if not token or token.upper() in {"NA", "N/A"}:
        return float("nan")
    m = _NUM.match(token)
    if not m:
        raise ValueError(f"Cannot parse number: {token!r}")
    value = float(m.group(1))
    unit = m.group(2).lower()
    combos = {
        "meg": 1e6,
        "ms": 1e-3,
        "us": 1e-6,
        "ns": 1e-9,
        "ps": 1e-12,
        "fs": 1e-15,
        "ma": 1e-3,
        "ua": 1e-6,
        "na": 1e-9,
        "pf": 1e-12,
        "nf": 1e-9,
        "uf": 1e-6,
        "ff": 1e-15,
        "kohm": 1e3,
        "mohm": 1e-3,
        "ohm": 1.0,
        "ohms": 1.0,
        "v": 1.0,
        "a": 1.0,
        "s": 1.0,
        "sec": 1.0,
    }
    if unit in combos:
        return value * combos[unit]
    prefixes = {
        "f": 1e-15,
        "p": 1e-12,
        "n": 1e-9,
        "u": 1e-6,
        "m": 1e-3,
        "k": 1e3,
        "g": 1e9,
        "t": 1e12,
    }
    if unit in prefixes:
        return value * prefixes[unit]
    if unit and unit[0] in prefixes and unit[1:] in {"", "s", "f", "a", "v", "ohm"}:
        return value * prefixes[unit[0]]
    return value


def _split_cols(line: str) -> list[str]:
    return [p for p in re.split(r"[\s,]+", line.strip()) if p]


def _parse_iv_block(lines: list[str], start: int) -> tuple[IvTable, int]:
    rows: list[list[float]] = []
    i = start
    while i < len(lines):
        raw = lines[i].strip()
        if not raw or raw.startswith("|") or raw.startswith("#"):
            i += 1
            continue
        if raw.startswith("["):
            break
        cols = _split_cols(raw.split("|")[0])
        if len(cols) < 2:
            i += 1
            continue
        try:
            vals = [_parse_number(c) for c in cols[:4]]
        except ValueError:
            break
        rows.append(vals + [float("nan")] * (4 - len(vals)))
        i += 1
    if not rows:
        raise ValueError("Empty IV table")
    arr = np.array(rows, dtype=float)
    v = arr[:, 0]
    i_typ = arr[:, 1]
    i_min = arr[:, 2] if arr.shape[1] > 2 and not np.all(np.isnan(arr[:, 2])) else None
    i_max = arr[:, 3] if arr.shape[1] > 3 and not np.all(np.isnan(arr[:, 3])) else None
    order = np.argsort(v)
    return (
        IvTable(
            v=v[order],
            i_typ=i_typ[order],
            i_min=None if i_min is None else i_min[order],
            i_max=None if i_max is None else i_max[order],
        ),
        i,
    )


def _parse_vt_block(
    lines: list[str], start: int, kind: WaveKind, header_vals: dict[str, float]
) -> tuple[VtWaveform, int]:
    rows: list[list[float]] = []
    i = start
    while i < len(lines):
        raw = lines[i].strip()
        if not raw or raw.startswith("|") or raw.startswith("#"):
            i += 1
            continue
        if raw.startswith("["):
            break
        upper = raw.upper()
        if upper.startswith("R_FIXTURE") or upper.startswith("V_FIXTURE"):
            parts = _split_cols(raw.split("|")[0])
            key = parts[0].lower()
            nums = [_parse_number(p) for p in parts[1:]]
            if key == "r_fixture":
                header_vals["r_fixture"] = nums[0]
            elif key == "v_fixture":
                header_vals["v_fixture"] = nums[0]
                if len(nums) > 1:
                    header_vals["v_fixture_min"] = nums[1]
                if len(nums) > 2:
                    header_vals["v_fixture_max"] = nums[2]
            i += 1
            continue
        cols = _split_cols(raw.split("|")[0])
        if len(cols) < 2:
            i += 1
            continue
        try:
            vals = [_parse_number(c) for c in cols[:4]]
        except ValueError:
            break
        rows.append(vals + [float("nan")] * (4 - len(vals)))
        i += 1
    if not rows:
        raise ValueError("Empty VT waveform")
    arr = np.array(rows, dtype=float)
    t = arr[:, 0]
    v_typ = arr[:, 1]
    v_min = arr[:, 2] if arr.shape[1] > 2 and not np.all(np.isnan(arr[:, 2])) else None
    v_max = arr[:, 3] if arr.shape[1] > 3 and not np.all(np.isnan(arr[:, 3])) else None
    order = np.argsort(t)
    wf = VtWaveform(
        kind=kind,
        r_fixture=header_vals.get("r_fixture", 50.0),
        v_fixture=header_vals.get("v_fixture", 0.0),
        v_fixture_min=header_vals.get("v_fixture_min"),
        v_fixture_max=header_vals.get("v_fixture_max"),
        t=t[order],
        v_typ=v_typ[order],
        v_min=None if v_min is None else v_min[order],
        v_max=None if v_max is None else v_max[order],
    )
    return wf, i


def parse_ibis(path: str | Path) -> IbisFile:
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    # Strip end-of-line comments starting with | but keep | inside? IBIS uses | as comment
    lines = text.splitlines()
    result = IbisFile(path=str(path))
    model: IbisModel | None = None
    i = 0
    while i < len(lines):
        raw = lines[i].strip()
        if not raw or raw.startswith("|") or raw.startswith("#"):
            i += 1
            continue
        # keyword
        if raw.startswith("["):
            m = re.match(r"\[([^\]]+)\]\s*(.*)$", raw)
            if not m:
                i += 1
                continue
            key = m.group(1).strip().lower()
            rest = m.group(2).strip()
            if key == "ibis ver":
                result.ibis_version = rest
            elif key == "file name":
                result.file_name = rest
            elif key == "model":
                name = rest
                model = IbisModel(name=name, source_path=str(path))
                result.models[name] = model
            elif key == "end":
                break
            elif model is not None:
                if key == "voltage range":
                    nums: list[float] = []
                    if rest:
                        cols = _split_cols(rest.split("|")[0])
                        nums = [_parse_number(c) for c in cols[:3]]
                    if len(nums) < 3:
                        i += 1
                        while i < len(lines) and (
                            not lines[i].strip() or lines[i].strip().startswith("|")
                        ):
                            i += 1
                        if i < len(lines):
                            cols = _split_cols(lines[i].split("|")[0])
                            nums = [_parse_number(c) for c in cols[:3]]
                    if len(nums) >= 3:
                        model.voltage_range = (nums[0], nums[1], nums[2])
                        model.vcc = nums[0]
                elif key == "pullup":
                    table, i = _parse_iv_block(lines, i + 1)
                    model.pullup = table
                    continue
                elif key == "pulldown":
                    table, i = _parse_iv_block(lines, i + 1)
                    model.pulldown = table
                    continue
                elif key == "power clamp":
                    table, i = _parse_iv_block(lines, i + 1)
                    model.power_clamp = table
                    continue
                elif key == "gnd clamp":
                    table, i = _parse_iv_block(lines, i + 1)
                    model.gnd_clamp = table
                    continue
                elif key == "rising waveform":
                    hdr: dict[str, float] = {}
                    wf, i = _parse_vt_block(lines, i + 1, WaveKind.RISING, hdr)
                    model.rising.append(wf)
                    continue
                elif key == "falling waveform":
                    hdr = {}
                    wf, i = _parse_vt_block(lines, i + 1, WaveKind.FALLING, hdr)
                    model.falling.append(wf)
                    continue
                elif key == "ramp":
                    i += 1
                    ramp = Ramp()
                    while i < len(lines):
                        r = lines[i].strip()
                        if not r or r.startswith("|"):
                            i += 1
                            continue
                        if r.startswith("["):
                            break
                        parts = _split_cols(r.split("|")[0])
                        if parts[0].lower() == "dv/dt_r" and len(parts) >= 2:
                            # format: num/num  or two numbers
                            token = parts[1]
                            if "/" in token:
                                a, b = token.split("/", 1)
                                # dv/dt as V/s approximated from ratio string like 2.0/0.5n
                                dv = _parse_number(a)
                                dt = _parse_number(b)
                                ramp.dv_dt_r_typ = dv / max(dt, 1e-18)
                            i += 1
                            continue
                        if parts[0].lower() == "dv/dt_f" and len(parts) >= 2:
                            token = parts[1]
                            if "/" in token:
                                a, b = token.split("/", 1)
                                dv = _parse_number(a)
                                dt = _parse_number(b)
                                ramp.dv_dt_f_typ = dv / max(dt, 1e-18)
                            i += 1
                            continue
                        if parts[0].lower() == "r_load":
                            ramp.r_load = _parse_number(parts[1])
                        i += 1
                    model.ramp = ramp
                    continue
            i += 1
            continue

        # non-keyword assignments inside model
        if model is not None:
            parts = _split_cols(raw.split("|")[0])
            key = parts[0].lower()
            if key == "model_type" and len(parts) > 1:
                model.model_type = parts[1]
            elif key == "polarity" and len(parts) > 1:
                model.polarity = parts[1]
            elif key == "c_comp" and len(parts) > 1:
                nums = [_parse_number(p) for p in parts[1:4]]
                model.c_comp = nums[0]
                if len(nums) > 1 and not np.isnan(nums[1]):
                    model.c_comp_min = nums[1]
                if len(nums) > 2 and not np.isnan(nums[2]):
                    model.c_comp_max = nums[2]
        i += 1

    return result


def list_models(path: str | Path) -> list[str]:
    return list(parse_ibis(path).models.keys())
