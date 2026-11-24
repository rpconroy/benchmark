"""Build a small local fixture for laptop smoke tests (config/local.yaml).

1. Copy 2 days of ARCO 2m_temperature -> data/local/zarr (native ARCO chunking).
2. Write the same data as daily netCDF4 files shaped like d633000 (VAR_2T, 27x139x277-style chunks).
3. Generate kerchunk refs for those netCDF files.

    python scripts/make_local_fixture.py [--overwrite]
"""
from pathlib import Path

import xarray as xr
from _common import load_config, parser

from era5bench.prep import build_kerchunk_refs, copy_zarr, write_refs


def main():
    p = parser(__doc__)
    p.set_defaults(config="config/local.yaml")
    a = p.parse_args()
    cfg = load_config(a.config)

    src, zdst = cfg.case("zarr-gcp"), cfg.case("zarr-local")
    copy_zarr(src, zdst, cfg.subset.time, zarr_format=cfg.prep.get("zarr_format", 2), overwrite=a.overwrite)

    nc = cfg.case("netcdf-local")
    ds = xr.open_dataset(zdst.url, engine="zarr", chunks=None)
    da = ds[zdst.variable].rename("VAR_2T")
    for path, (_, day) in zip(nc.urls, da.groupby("time.dayofyear")):
        path = Path(path)
        if path.exists() and not a.overwrite:
            print(f"[skip] {path}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        enc = {"VAR_2T": {"zlib": True, "complevel": 1, "shuffle": True,
                          "chunksizes": (min(27, day.sizes["time"]), 139, 277)}}
        day.to_dataset().to_netcdf(path, engine="h5netcdf", encoding=enc)
        print(f"[nc  ] wrote {path}")

    kc = cfg.case("kerchunk-local")
    if not Path(kc.refs).exists() or a.overwrite:
        write_refs(build_kerchunk_refs(kc, cfg), kc.refs)


if __name__ == "__main__":
    main()
