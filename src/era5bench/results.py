"""Summarise benchmark CSVs.

    python -m era5bench.results results/*.csv
    python -m era5bench.results results/*.csv --warm-only --metric read_s
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd


def load(paths: list[str]) -> pd.DataFrame:
    return pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)


def summarise(df: pd.DataFrame, metric: str = "total_s", warm_only: bool = False) -> pd.DataFrame:
    ok = df[df["status"] == "ok"]
    if warm_only:
        ok = ok[~ok["cold"].astype(str).str.lower().eq("true")]
    g = ok.groupby(["workload", "format", "platform", "case"])[metric]
    out = g.agg(["count", "median", "min", "max"]).reset_index()
    cold = (
        df[(df["status"] == "ok") & df["cold"].astype(str).str.lower().eq("true")]
        .groupby(["workload", "case"])[metric].median().rename("cold").reset_index()
    )
    out = out.merge(cold, on=["workload", "case"], how="left") if not warm_only else out
    return out.sort_values(["workload", "median"])


def check_consistency(df: pd.DataFrame, rtol: float = 1e-4) -> pd.DataFrame:
    """Per workload: each case's check value and its relative difference from the median across cases."""
    ok = df[(df["status"] == "ok") & (df["workload"] != "open_only")]
    per = ok.groupby(["workload", "case"])["check"].median().reset_index()
    ref = per.groupby("workload")["check"].transform("median")
    per["rel_diff"] = (per["check"] - ref).abs() / ref.abs()
    per["consistent"] = per["rel_diff"] <= rtol
    return per


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="+")
    p.add_argument("--metric", default="total_s", choices=["total_s", "open_s", "read_s"])
    p.add_argument("--warm-only", action="store_true", help="exclude repeat 0")
    a = p.parse_args(argv)

    df = load(a.csv)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 500)
    print(f"== {a.metric} (seconds) ==")
    print(summarise(df, a.metric, a.warm_only).to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print("\n== check-value consistency across cases ==")
    print(check_consistency(df).to_string(index=False))
    bad = df[df["status"] != "ok"]
    if len(bad):
        print(f"\n== {len(bad)} failed runs ==")
        print(bad[["case", "workload", "repeat", "status", "error"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
