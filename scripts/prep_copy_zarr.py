"""Copy the ARCO-ERA5 2t subset (with its native chunking) to every zarr target case.

The first target is copied from the source (GCS). Later targets are copied from
the first target, which should be a fast local one (Lustre), so we don't
re-download from GCS.

    python scripts/prep_copy_zarr.py -c config/sites.yaml
    python scripts/prep_copy_zarr.py -c config/sites.yaml --only zarr-boreas
"""
from _common import load_config, parser, write_options

from era5bench.prep import copy_zarr


def main():
    a = parser(__doc__).parse_args()
    cfg = load_config(a.config)
    src = cfg.case(cfg.prep["zarr_source"])
    targets = [cfg.case(n) for n in cfg.prep["zarr_targets"]]
    zf = cfg.prep.get("zarr_format", 2)
    first = targets[0]
    for i, dst in enumerate(targets):
        if a.only and dst.name not in a.only:
            continue
        from_case = src if i == 0 else first
        copy_zarr(from_case, dst, cfg.subset.time, write_options=write_options(cfg, dst),
                  zarr_format=zf, overwrite=a.overwrite)


if __name__ == "__main__":
    main()
