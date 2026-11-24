"""Open each (format, platform) case as an xarray Dataset with an explicit engine.

Every opener returns a dataset normalised to a single variable ``t2m`` with
dims ``(time, latitude, longitude)``, restricted to the configured time range.
"""

from __future__ import annotations

from typing import Any

import fsspec
import xarray as xr

from .config import Case, Config

VAR = "t2m"

DEFAULT_ENGINES = {"zarr": "zarr", "netcdf": "h5netcdf", "kerchunk": "zarr"}


def protocol_of(url: str) -> str:
    """Return the fsspec protocol for a url/path ('file' for plain paths)."""
    return fsspec.utils.get_protocol(url)


def _is_opendap(url: str) -> bool:
    return protocol_of(url) in ("http", "https") and "/dodsC/" in url


def _chunks(cfg: Config, case: Case) -> Any:
    # None -> no dask for single stores (zarr/kerchunk use zarr's own concurrent fetching);
    #         open_mfdataset (netCDF) always uses dask with the files' on-disk chunks.
    # {}   -> dask with on-disk chunks. Global `dask.chunks`, per-case `chunks` overrides it.
    if case.chunks != "default":
        return case.chunks
    return cfg.dask.get("chunks", None)


def open_zarr_case(case: Case, cfg: Config) -> xr.Dataset:
    so = case.storage_options or None
    return xr.open_dataset(
        case.url,
        engine=case.engine or "zarr",
        chunks=_chunks(cfg, case),
        storage_options=so,
        # TODO: some zarr stores lack consolidated metadata; make configurable if needed.
        consolidated=None,
    )


def open_netcdf_case(case: Case, cfg: Config) -> xr.Dataset:
    urls = case.urls
    first = urls[0]
    chunks = _chunks(cfg, case)
    kw: dict[str, Any] = dict(combine="by_coords", parallel=False, chunks=chunks)

    if _is_opendap(first):
        # OPeNDAP: pass the URLs straight to netCDF4-C.
        return xr.open_mfdataset(urls, engine=case.engine or "netcdf4", **kw)

    proto = protocol_of(first)
    if proto == "file":
        return xr.open_mfdataset(urls, engine=case.engine or "h5netcdf", **kw)

    # Remote object storage (s3, gs, https byte-range): open fsspec file objects
    # and let h5netcdf read through them.
    fs = fsspec.filesystem(proto, **(case.storage_options or {}))
    files = [fs.open(u, mode="rb", **(case.open_options or {})) for u in urls]
    return xr.open_mfdataset(files, engine=case.engine or "h5netcdf", **kw)


def kerchunk_storage_options(case: Case, cfg: Config) -> dict[str, Any]:
    target = cfg.case(case.netcdf_case)
    so: dict[str, Any] = {
        "fo": case.refs,
        "remote_protocol": protocol_of(target.urls[0]),
        "remote_options": target.storage_options or {},
        "asynchronous": True,  # required by zarr>=3 (async store)
    }
    if protocol_of(case.refs) != "file":
        so["target_protocol"] = protocol_of(case.refs)
        so["target_options"] = case.refs_storage_options or {}
    return so


def open_kerchunk_case(case: Case, cfg: Config) -> xr.Dataset:
    return xr.open_dataset(
        "reference://",
        engine=case.engine or "zarr",
        chunks=_chunks(cfg, case),
        storage_options=kerchunk_storage_options(case, cfg),
        consolidated=False,
        zarr_format=2,  # kerchunk references describe a zarr v2 store
    )


OPENERS = {
    "zarr": open_zarr_case,
    "netcdf": open_netcdf_case,
    "kerchunk": open_kerchunk_case,
}


def normalise(ds: xr.Dataset, case: Case, cfg: Config) -> xr.Dataset:
    """Select the variable and time range, and rename the variable to ``t2m``."""
    if case.variable not in ds:
        raise KeyError(f"{case.name}: variable {case.variable!r} not in {list(ds.data_vars)[:20]}")
    ds = ds[[case.variable]].rename({case.variable: VAR})
    rename = {k: v for k, v in {"lat": "latitude", "lon": "longitude"}.items() if k in ds.dims}
    if rename:
        ds = ds.rename(rename)
    t0, t1 = cfg.subset.time
    ds = ds.sel(time=slice(t0, t1))
    return ds


def open_case(case: Case, cfg: Config) -> xr.Dataset:
    ds = OPENERS[case.format](case, cfg)
    return normalise(ds, case, cfg)
