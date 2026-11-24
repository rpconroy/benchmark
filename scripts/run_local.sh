#!/bin/bash
# Laptop smoke test: build the 2-day fixture (once) and run every local case once.
set -euo pipefail
cd "$(dirname "$0")/.."
python scripts/make_local_fixture.py
python -m era5bench.runner -c config/local.yaml --repeats 1 -o results/local_smoke.csv
python -m era5bench.results results/local_smoke.csv
