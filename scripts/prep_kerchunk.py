"""Generate kerchunk reference JSON for each kerchunk case, pointing at its netcdf_case files.

    python scripts/prep_kerchunk.py -c config/sites.yaml
"""
from _common import load_config, parser

from era5bench.prep import _exists, build_kerchunk_refs, write_refs


def main():
    a = parser(__doc__).parse_args()
    cfg = load_config(a.config)
    for name in cfg.prep["kerchunk_cases"]:
        if a.only and name not in a.only:
            continue
        case = cfg.case(name)
        wo = (cfg.prep.get("write_options") or {}).get(case.platform, case.refs_storage_options)
        if _exists(case.refs, wo) and not a.overwrite:
            print(f"[skip] {case.refs} exists (use --overwrite)")
            continue
        refs = build_kerchunk_refs(case, cfg)
        write_refs(refs, case.refs, wo)


if __name__ == "__main__":
    main()
