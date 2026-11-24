"""Shared CLI helpers for the prep scripts."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # works without `pip install -e .`

from era5bench.config import load_config  # noqa: E402


def parser(doc: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-c", "--config", default="config/sites.yaml")
    p.add_argument("--only", nargs="*", help="limit to these target case names")
    p.add_argument("--overwrite", action="store_true", help="replace existing targets")
    return p


def write_options(cfg, case):
    """Write credentials for a platform, from prep.write_options.<platform> (falls back to read options)."""
    wo = (cfg.prep.get("write_options") or {}).get(case.platform)
    return wo if wo is not None else (case.storage_options or None)
