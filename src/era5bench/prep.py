"""Data staging: copy zarr subsets, copy/upload netCDF, generate kerchunk refs.

Nothing in here runs during benchmarking. The thin CLIs in ``scripts/`` call
these functions.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import fsspec
import xarray as xr

from .config import Case, Config
from .openers import protocol_of

# Encoding keys worth carrying from the source store into the copy.
_KEEP_VAR_ENC = {"chunks", "compressor", "compressors", "filters", "serializer", "dtype",
                 "_FillValue", "scale_factor", "add_offset", "units", "calendar"}
_KEEP_COORD_ENC = {"dtype", "units", "calendar", "_FillValue"}


def _exists(url: str, storage_options: dict | None) -> bool:
    fs, path = fsspec.core.url_to_fs(url, **(storage_options or {}))
    return fs.exists(path)


def _rm(url: str, storage_options: dict | None) -> None:
    fs, path = fsspec.core.url_to_fs(url, **(storage_options or {}))
    if fs.exists(path):
        fs.rm(path, recursive=True)


def subset_zarr_source(src: Case, time: tuple[str, str]) -> xr.Dataset:
    """Open the source zarr lazily with its native chunks and cut variable + time range."""
    ds = xr.open_dataset(src.url, engine="zarr", chunks={}, storage_options=src.storage_options or None)
    sub = ds[[src.variable]].sel(time=slice(*time))
    # Drop non-index coords the variable doesn't need (keeps the copy minimal).
    sub = sub.drop_vars([c for c in sub.coords if c not in sub[src.variable].dims])
    for name, var in sub.variables.items():
        keep = _KEEP_VAR_ENC if name == src.variable else _KEEP_COORD_ENC
        var.encoding = {k: v for k, v in var.encoding.items() if k in keep}
    return sub


def copy_zarr(src: Case, dst: Case, time: tuple[str, str], *, write_options: dict | None = None,
              zarr_format: int | None = 2, overwrite: bool = False) -> None:
    """Copy ``src.variable`` over ``time`` from src store to dst store, keeping chunking/compression."""
    so = write_options if write_options is not None else (dst.storage_options or None)
    if _exists(dst.url, so):
        if not overwrite:
            print(f"[skip] {dst.url} exists (use --overwrite)")
            return
        _rm(dst.url, so)
    sub = subset_zarr_source(src, time)
    if dst.variable != src.variable:
        sub = sub.rename({src.variable: dst.variable})
    enc = sub[dst.variable].encoding
    print(f"[zarr] {src.url} -> {dst.url}  shape={dict(sub.sizes)} chunks={enc.get('chunks')} "
          f"size={sub[dst.variable].nbytes / 1e9:.2f} GB")
    sub.to_zarr(dst.url, mode="w", storage_options=so, consolidated=True, zarr_format=zarr_format,
                compute=True)


def copy_netcdf(src: Case, dst: Case, *, write_options: dict | None = None, overwrite: bool = False) -> None:
    """Copy src.urls -> dst.urls, matched by basename. Local copy or upload to object storage."""
    by_name = {os.path.basename(u): u for u in src.urls}
    so = write_options if write_options is not None else (dst.storage_options or {})
    for d in dst.urls:
        name = os.path.basename(d)
        if name not in by_name:
            raise ValueError(f"{dst.name}: {name} has no matching file in {src.name}")
        s = by_name[name]
        proto = protocol_of(d)
        if proto == "file":
            Path(d).parent.mkdir(parents=True, exist_ok=True)
            if Path(d).exists() and not overwrite and Path(d).stat().st_size == Path(s).stat().st_size:
                print(f"[skip] {d} exists")
                continue
            print(f"[copy] {s} -> {d}")
            shutil.copyfile(s, d)
        else:
            fs = fsspec.filesystem(proto, **so)
            if fs.exists(d) and not overwrite and fs.size(d) == os.path.getsize(s):
                print(f"[skip] {d} exists")
                continue
            print(f"[put ] {s} -> {d}")
            fs.put_file(s, d)


def build_kerchunk_refs(case: Case, cfg: Config, *, inline_threshold: int = 300) -> dict[str, Any]:
    """Generate combined kerchunk refs for the netCDF files of ``case.netcdf_case``."""
    from kerchunk.combine import MultiZarrToZarr
    from kerchunk.hdf import SingleHdf5ToZarr

    target = cfg.case(case.netcdf_case)
    proto = protocol_of(target.urls[0])
    so = target.storage_options or {}
    singles = []
    for u in target.urls:
        print(f"[refs] scanning {u}")
        with fsspec.open(u, "rb", **so) as f:
            singles.append(SingleHdf5ToZarr(f, u, inline_threshold=inline_threshold).translate())
    if len(singles) == 1:
        return singles[0]
    mzz = MultiZarrToZarr(
        singles,
        remote_protocol=proto,
        remote_options=so,
        concat_dims=["time"],
        identical_dims=["latitude", "longitude"],
        coo_map={"time": "cf:time"},  # decode CF time, so files with different epochs concat correctly
    )
    return mzz.translate()


def write_refs(refs: dict, url: str, storage_options: dict | None = None) -> None:
    if protocol_of(url) == "file":
        Path(url).parent.mkdir(parents=True, exist_ok=True)
    with fsspec.open(url, "w", **(storage_options or {})) as f:
        json.dump(refs, f)
    print(f"[refs] wrote {url}")
