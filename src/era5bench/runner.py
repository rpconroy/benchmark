"""Run the benchmark matrix: each (repeat, case, workload) runs in a fresh subprocess.

Repeats are the outermost loop, so cases are interleaved in time. That way slow
drift (filesystem load, network) doesn't bias any one case. Repeat 0 is flagged
``cold``. Note that the OS page cache can't be dropped without root, so later
local-disk repeats may be served partly from memory.

    python -m era5bench.runner -c config/sites.yaml
    python -m era5bench.runner -c config/sites.yaml --cases zarr-lustre netcdf-lustre --repeats 3
    python -m era5bench.runner -c config/sites.yaml --dry-run
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

from .config import load_config
from .workloads import WORKLOADS

FIELDS = [
    "timestamp", "host", "pbs_jobid", "config", "case", "format", "platform", "workload",
    "repeat", "cold", "status", "open_s", "read_s", "total_s", "check", "nbytes", "ntime",
    "dask_chunks", "dask_scheduler", "error",
]


def run_one(config: str, case: str, workload: str, timeout: float) -> dict:
    cmd = [sys.executable, "-m", "era5bench.worker", "-c", config, "--case", case, "--workload", workload]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": f"exceeded {timeout}s"}
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln.startswith("{")]
    if not lines:
        return {"status": "error", "error": (proc.stderr or proc.stdout).strip()[-500:]}
    out = json.loads(lines[-1])
    if out.get("status") != "ok":
        sys.stderr.write(out.get("traceback", "") + "\n")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-c", "--config", required=True)
    p.add_argument("--cases", nargs="*", help="case names (default: all enabled)")
    p.add_argument("--workloads", nargs="*", choices=list(WORKLOADS), help="default: all")
    p.add_argument("--repeats", type=int, help="override run.repeats")
    p.add_argument("--timeout", type=float, help="per-run timeout seconds (override run.timeout_s)")
    p.add_argument("-o", "--output", help="CSV path (default results/<config>_<timestamp>.csv)")
    p.add_argument("--dry-run", action="store_true", help="list the matrix and exit")
    a = p.parse_args(argv)

    cfg = load_config(a.config)
    if a.cases:
        cases = [cfg.case(n) for n in a.cases]  # explicit request runs even if disabled
    else:
        cases = [c for c in cfg.cases.values() if c.enabled]
    workloads = a.workloads or list(cfg.run.get("workloads", WORKLOADS))
    repeats = a.repeats or int(cfg.run.get("repeats", 5))
    timeout = a.timeout or float(cfg.run.get("timeout_s", 1800))

    print(f"{len(cases)} cases x {len(workloads)} workloads x {repeats} repeats")
    for c in cases:
        print(f"  {c.name:24s} {c.format:9s} {c.platform}")
    if a.dry_run:
        return 0

    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    out = Path(a.output or f"results/{Path(a.config).stem}_{stamp}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    new = not out.exists()
    host = socket.gethostname()

    with out.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for rep in range(repeats):
            for c in cases:
                for wl in workloads:
                    res = run_one(str(cfg.path), c.name, wl, timeout)
                    row = {
                        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
                        "host": host,
                        "pbs_jobid": os.environ.get("PBS_JOBID", ""),
                        "config": str(cfg.path),
                        "case": c.name,
                        "format": c.format,
                        "platform": c.platform,
                        "workload": wl,
                        "repeat": rep,
                        "cold": rep == 0,
                        "dask_chunks": json.dumps(cfg.dask.get("chunks")),
                        "dask_scheduler": cfg.dask.get("scheduler", "threads"),
                        **res,
                    }
                    w.writerow(row)
                    fh.flush()
                    t = res.get("total_s")
                    tstr = f"{t:8.2f}s" if isinstance(t, float) else f"{res['status']:>9s}"
                    print(f"[rep {rep}] {c.name:24s} {wl:14s} {tstr}  check={res.get('check', '')}", flush=True)
                    if res["status"] != "ok":
                        print(f"          ! {res.get('error', '')[:300]}", flush=True)

    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
