# benchmark

This repo benchmarks ERA5 read performance across formats (zarr, kerchunk, netCDF) and storage platforms (GCP, Boreas S3, Campaign Store, Lustre, GDEX TDS) on NCAR Casper. All reads go through xarray with an explicit `engine=`.

The test subset is **ERA5 2 m temperature, 2020-01-01 → 2020-02-29** (1440 hourly steps, 0.25°, ~6 GB). Project rules and the list of open questions are in [CLAUDE.md](CLAUDE.md).

## Matrix
| | GCP | Boreas | Campaign | Lustre | TDS |
|---|---|---|---|---|---|
| **zarr** (ARCO chunks 1×721×1440, blosc-lz4) | ARCO original | copy | copy | copy | – |
| **netCDF** (d633000, chunks 27×139×277, zlib) | – | upload | original | copy | OPeNDAP |
| **kerchunk** (refs → netCDF) | – | ✓ | ✓ (+ GDEX refs, TBD) | ✓ | – |

Workloads:
- `open_only`: open the store and parse metadata.
- `global_field`: one timestep over the full grid.
- `point_series`: Boulder, all timesteps.
- `regional_mean`: CONUS box, all timesteps, reduced to a mean.

The zarr and netCDF files differ in chunking. A point series on ARCO's time=1 chunks reads every chunk in the time range, so per-format results reflect chunk layout as well as storage speed.

## Setup (Casper)
```bash
cd /glade/campaign/collections/gdex/data/exchange/benchmark_test
git clone <this repo> && cd benchmark
module load conda
conda env create -f environment.yml && conda activate era5bench
pip install -e .
```
First fill in the `TODO(verify)` entries in `config/sites.yaml`: Boreas prefix and write profile, ARCO store choice, GDEX kerchunk refs. Also set the PBS project code in `scripts/run_casper.pbs`.

## Stage data (one time, run from a Casper login or compute node)
```bash
python scripts/prep_copy_zarr.py    # ARCO subset -> Lustre, then Lustre -> Campaign, Boreas
python scripts/prep_copy_netcdf.py  # d633000 files -> Lustre, Boreas
python scripts/prep_kerchunk.py     # refs for campaign / lustre / boreas netCDF
```
Each script takes `--only <case>` and `--overwrite`. Boreas writes use `prep.write_options.boreas` (an AWS profile, or `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`).

## Run
```bash
python -m era5bench.runner -c config/sites.yaml --dry-run           # show the matrix
qsub scripts/run_casper.pbs                                         # full run (5 repeats)
qsub -v ARGS="--cases zarr-lustre kerchunk-lustre --repeats 2" scripts/run_casper.pbs
python -m era5bench.results results/sites_*.csv [--warm-only] [--metric read_s]
```
Each measurement runs in a fresh Python process and records `open_s`, `read_s` and `total_s`, plus a `check` value. The summary checks that every case reads identical numbers. Repeats are interleaved across cases, and repeat 0 is marked `cold`.

**Caveat:** we can't drop the OS page cache without root, so warm repeats on Campaign and Lustre may be partly served from node memory. Compare `cold` against warm, or spread repeats across jobs and nodes.

## Laptop smoke test
```bash
conda activate era5bench && pip install -e .
pytest -q                # offline synthetic fixture
scripts/run_local.sh     # 2-day ARCO slice -> local zarr / netCDF / kerchunk + GCP
```
