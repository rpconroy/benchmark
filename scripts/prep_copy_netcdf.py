"""Copy the d633000 netCDF files to Lustre and upload them to Boreas.

    python scripts/prep_copy_netcdf.py -c config/sites.yaml
"""
from _common import load_config, parser, write_options

from era5bench.prep import copy_netcdf


def main():
    a = parser(__doc__).parse_args()
    cfg = load_config(a.config)
    src = cfg.case(cfg.prep["netcdf_source"])
    for name in cfg.prep["netcdf_targets"]:
        if a.only and name not in a.only:
            continue
        dst = cfg.case(name)
        copy_netcdf(src, dst, write_options=write_options(cfg, dst), overwrite=a.overwrite)


if __name__ == "__main__":
    main()
