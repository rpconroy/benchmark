"""Run ONE timed (case, workload) measurement and print a JSON line.

Run by ``era5bench.runner`` in a fresh subprocess, so caches don't carry over
between repeats.

    python -m era5bench.worker -c config/sites.yaml --case zarr-lustre --workload point_series
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback

from .config import Config, load_config


def configure_dask(cfg: Config) -> dict:
    import dask

    scheduler = cfg.dask.get("scheduler", "threads")
    settings = {"scheduler": scheduler}
    if cfg.dask.get("num_workers"):
        settings["num_workers"] = int(cfg.dask["num_workers"])
    dask.config.set(settings)
    return settings


def measure(cfg: Config, case_name: str, workload: str) -> dict:
    from .openers import open_case
    from .workloads import WORKLOADS

    case = cfg.case(case_name)
    fn = WORKLOADS[workload]
    configure_dask(cfg)

    t0 = time.perf_counter()
    ds = open_case(case, cfg)
    t1 = time.perf_counter()
    check, nbytes = fn(ds, cfg.subset)
    t2 = time.perf_counter()
    ds.close()

    return {
        "status": "ok",
        "open_s": t1 - t0,
        "read_s": t2 - t1,
        "total_s": t2 - t0,
        "check": check,
        "nbytes": nbytes,
        "ntime": int(ds.sizes.get("time", 0)),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-c", "--config", required=True)
    p.add_argument("--case", required=True)
    p.add_argument("--workload", required=True)
    a = p.parse_args(argv)

    cfg = load_config(a.config)
    try:
        out = measure(cfg, a.case, a.workload)
    except Exception as e:  # report failures as data rather than crashing the run
        out = {"status": "error", "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}
    print(json.dumps(out))
    return 0 if out["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
