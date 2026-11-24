"""Read patterns that are benchmarked.

Each workload takes a normalised dataset (see ``openers.normalise``) and the
subset config, triggers the actual I/O, and returns ``(check_value, nbytes)``.
``check_value`` is a scalar that should agree across all cases reading the same
data, which lets us confirm they really read the same values.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import xarray as xr

from .config import Subset
from .openers import VAR


def _lat_slice(da: xr.DataArray, lo: float, hi: float) -> slice:
    lat = da["latitude"].values
    lo, hi = min(lo, hi), max(lo, hi)
    return slice(hi, lo) if lat[0] > lat[-1] else slice(lo, hi)


def _lon(da: xr.DataArray, lon: float) -> float:
    # Datasets here use 0..360; accept -180..180 in config.
    if float(da["longitude"].min()) >= 0 and lon < 0:
        lon += 360.0
    return lon


def open_only(ds: xr.Dataset, subset: Subset) -> tuple[float, int]:
    """No data read; opening + metadata parsing is timed by the worker."""
    _ = ds[VAR].attrs, ds.sizes
    return float(ds.sizes["time"]), 0


def global_field(ds: xr.Dataset, subset: Subset) -> tuple[float, int]:
    """One timestep, full 0.25° global grid."""
    arr = ds[VAR].sel(time=subset.global_field_time).values
    return float(np.nanmean(arr)), arr.nbytes


def point_series(ds: xr.Dataset, subset: Subset) -> tuple[float, int]:
    """Full time range at one grid point (worst case for spatially chunked data)."""
    da = ds[VAR]
    arr = da.sel(
        latitude=subset.point["latitude"],
        longitude=_lon(da, subset.point["longitude"]),
        method="nearest",
    ).values
    return float(np.nanmean(arr)), arr.nbytes


def regional_mean(ds: xr.Dataset, subset: Subset) -> tuple[float, int]:
    """Lat/lon box over the full time range, reduced to a scalar mean."""
    da = ds[VAR]
    la, lb = subset.box["latitude"]
    oa, ob = (_lon(da, x) for x in subset.box["longitude"])
    sub = da.sel(latitude=_lat_slice(da, la, lb), longitude=slice(min(oa, ob), max(oa, ob)))
    nbytes = int(sub.size * sub.dtype.itemsize)
    return float(sub.mean().values), nbytes


WORKLOADS: dict[str, Callable[[xr.Dataset, Subset], tuple[float, int]]] = {
    "open_only": open_only,
    "global_field": global_field,
    "point_series": point_series,
    "regional_mean": regional_mean,
}
