"""Offline tests: build a tiny synthetic ERA5-like fixture in zarr, netCDF and kerchunk,
then check that every case returns identical values for every workload."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import xarray as xr
import yaml

from era5bench.config import load_config
from era5bench.prep import build_kerchunk_refs, write_refs
from era5bench.runner import main as runner_main
from era5bench.worker import measure
from era5bench.workloads import WORKLOADS


@pytest.fixture(scope="module")
def cfg(tmp_path_factory):
    d = tmp_path_factory.mktemp("fx")
    time = pd.date_range("2020-01-01", periods=48, freq="h")
    lat = np.arange(90, -90.1, -2.5)
    lon = np.arange(0, 360, 2.5)
    rng = np.random.default_rng(0)
    data = (250 + 30 * rng.random((time.size, lat.size, lon.size))).astype("float32")
    ds = xr.Dataset({"2m_temperature": (("time", "latitude", "longitude"), data)},
                    coords={"time": time, "latitude": lat, "longitude": lon})

    zpath = str(d / "t.zarr")
    ds.chunk({"time": 1}).to_zarr(zpath, zarr_format=2, consolidated=True)

    nc = []
    for i, (_, day) in enumerate(ds.rename({"2m_temperature": "VAR_2T"}).groupby("time.dayofyear")):
        p = str(d / f"t{i}.nc")
        day.to_netcdf(p, engine="h5netcdf",
                      encoding={"VAR_2T": {"zlib": True, "chunksizes": (12, 20, 40)}})
        nc.append(p)

    raw = {
        "subset": {"time": ["2020-01-01T00", "2020-01-02T23"], "global_field_time": "2020-01-01T12",
                   "point": {"latitude": 40, "longitude": -105}, "box": {"latitude": [25, 50],
                                                                          "longitude": [-125, -65]}},
        "dask": {"chunks": None, "scheduler": "synchronous"},
        "run": {"repeats": 1},
        "cases": [
            {"name": "z", "format": "zarr", "platform": "t", "url": zpath, "variable": "2m_temperature"},
            {"name": "n", "format": "netcdf", "platform": "t", "urls": nc, "variable": "VAR_2T"},
            {"name": "k", "format": "kerchunk", "platform": "t", "netcdf_case": "n",
             "refs": str(d / "refs.json"), "variable": "VAR_2T"},
        ],
    }
    cpath = d / "cfg.yaml"
    cpath.write_text(yaml.safe_dump(raw))
    c = load_config(cpath)
    write_refs(build_kerchunk_refs(c.case("k"), c), c.case("k").refs)
    return c


@pytest.mark.parametrize("workload", list(WORKLOADS))
def test_cases_agree(cfg, workload):
    results = {name: measure(cfg, name, workload) for name in cfg.cases}
    checks = {n: r["check"] for n, r in results.items()}
    assert all(r["status"] == "ok" for r in results.values())
    assert all(r["ntime"] == 48 for r in results.values())
    vals = list(checks.values())
    assert np.allclose(vals, vals[0]), checks


def test_runner_end_to_end(cfg, tmp_path):
    out = tmp_path / "r.csv"
    assert runner_main(["-c", str(cfg.path), "--workloads", "global_field", "-o", str(out)]) == 0
    df = pd.read_csv(out)
    assert len(df) == 3 and (df["status"] == "ok").all()
