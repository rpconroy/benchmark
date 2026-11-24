"""Load benchmark configuration (config/*.yaml) into simple dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

FORMATS = ("zarr", "netcdf", "kerchunk")


@dataclass
class Subset:
    time: tuple[str, str]
    global_field_time: str
    point: dict[str, float]  # {"latitude": .., "longitude": ..}
    box: dict[str, list[float]]  # {"latitude": [a, b], "longitude": [a, b]}


@dataclass
class Case:
    name: str
    format: str
    platform: str
    variable: str
    enabled: bool = True
    # zarr: single store url/path. netcdf: list of files/urls. kerchunk: refs file.
    url: str | None = None
    urls: list[str] = field(default_factory=list)
    refs: str | None = None
    netcdf_case: str | None = None  # kerchunk: which netcdf case the refs point at
    engine: str | None = None  # override the default engine for the format
    chunks: Any = "default"  # per-case override of dask.chunks (e.g. bigger requests for OPeNDAP)
    storage_options: dict[str, Any] = field(default_factory=dict)
    refs_storage_options: dict[str, Any] = field(default_factory=dict)
    open_options: dict[str, Any] = field(default_factory=dict)  # fsspec .open() kwargs
    notes: str = ""


@dataclass
class Config:
    path: Path
    subset: Subset
    cases: dict[str, Case]
    dask: dict[str, Any] = field(default_factory=dict)
    run: dict[str, Any] = field(default_factory=dict)
    prep: dict[str, Any] = field(default_factory=dict)

    def case(self, name: str) -> Case:
        try:
            return self.cases[name]
        except KeyError:
            raise KeyError(f"unknown case {name!r}; known: {sorted(self.cases)}") from None


def load_config(path: str | Path) -> Config:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())

    s = raw["subset"]
    subset = Subset(
        time=(str(s["time"][0]), str(s["time"][1])),
        global_field_time=str(s["global_field_time"]),
        point={k: float(v) for k, v in s["point"].items()},
        box={k: [float(x) for x in v] for k, v in s["box"].items()},
    )

    cases: dict[str, Case] = {}
    for c in raw.get("cases", []):
        case = Case(**c)
        if case.format not in FORMATS:
            raise ValueError(f"case {case.name}: format must be one of {FORMATS}")
        if case.name in cases:
            raise ValueError(f"duplicate case name {case.name}")
        cases[case.name] = case

    for case in cases.values():
        if case.format == "zarr" and not case.url:
            raise ValueError(f"zarr case {case.name} needs `url`")
        if case.format == "netcdf" and not case.urls:
            raise ValueError(f"netcdf case {case.name} needs `urls`")
        if case.format == "kerchunk":
            if not case.refs or not case.netcdf_case:
                raise ValueError(f"kerchunk case {case.name} needs `refs` and `netcdf_case`")
            if case.netcdf_case not in cases:
                raise ValueError(f"kerchunk case {case.name}: unknown netcdf_case {case.netcdf_case}")

    return Config(
        path=path,
        subset=subset,
        cases=cases,
        dask=raw.get("dask", {}) or {},
        run=raw.get("run", {}) or {},
        prep=raw.get("prep", {}) or {},
    )
