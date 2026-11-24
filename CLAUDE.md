# CLAUDE.md

Guidance for Claude (and humans) working in this repo.

## What this project is
This project benchmarks how fast **ERA5 2m temperature** reads with xarray, comparing **formats** and **storage platforms**. It runs on NCAR's **Casper** HPC.

| format \ platform | GCP (ARCO-ERA5) | Boreas (GDEX on-prem S3) | Campaign Store | Lustre | GDEX TDS |
|---|---|---|---|---|---|
| zarr     | original | copy of ARCO subset | copy of ARCO subset | copy of ARCO subset | – |
| netCDF   | – | upload of d633000 files | d633000 original | copy of d633000 files | OPeNDAP |
| kerchunk | – | refs → Boreas netCDF | refs → campaign netCDF (+ existing GDEX refs) | refs → Lustre netCDF | – |

Default test subset: `2m temperature`, **2020-01-01 → 2020-02-29**, hourly, 0.25°. Keep it at **two months or less** unless the user says otherwise.

## ALWAYS ASK, NEVER GUESS
**Ask the user before assuming any of the following.** Do not invent a value that only looks plausible:
- URLs: TDS/OPeNDAP paths, S3 endpoints, bucket names, prefixes, GCS store names.
- Filesystem paths on GLADE, Campaign or Lustre.
- Credentials and how they are supplied. Never write keys into the repo.
- Dataset IDs, file naming patterns, variable names, chunking choices.
- Whether a copy or upload is allowed to overwrite existing data.
- PBS project codes, queues, wall times.

Unverified values live in `config/sites.yaml` and are marked `# TODO(verify)`. Ask about them; don't silently "fix" them. If a task is ambiguous (scope, which cases to run, how to interpret results), ask a short clarifying question before writing a lot of code.

## Known facts (confirmed by the user)
- GCP source: Google ARCO-ERA5, `gs://gcp-public-data-arco-era5`, read anonymously.
- Boreas endpoint: `https://boreas.hpc.ucar.edu`, bucket `gdex-data2`. Reads are anonymous. Writes need credentials (AWS profile or env vars).
- The zarr copies on Boreas, Campaign and Lustre are copies of the **ARCO subset**, so chunking stays identical to GCP.
- d633000 netCDF on campaign: `/glade/campaign/collections/gdex/data/d633000/`.
- Writable campaign scratch, where this repo is cloned: `/glade/campaign/collections/gdex/data/exchange/benchmark_test`.
- Lustre work dir: `/lustre/desc1/gdex/work/rpconroy/benchmark`.
- TDS is benchmarked over **OPeNDAP** only.
- GDEX publishes kerchunk refs for d633000. Their location is TODO(verify). We also generate our own refs.
- Workloads: open/metadata, single-time global field, point time series, regional mean.

## Coding conventions
- Python ≥ 3.11 and **xarray**. Open data with `xr.open_dataset` (or `xr.open_mfdataset` for multi-file netCDF) and **always pass an explicit `engine=`**:
  - zarr → `engine="zarr"`
  - local or S3 netCDF → `engine="h5netcdf"`
  - OPeNDAP → `engine="netcdf4"`
  - kerchunk → `engine="zarr"` on `reference://` with `storage_options={"fo": ...}`
- All site-specific values come from `config/*.yaml`. Never hard-code paths or URLs in `src/`.
- Every case must normalise to the variable name `t2m` with dims `(time, latitude, longitude)`, so all cases run the same workload code.
- Each timed run happens in a **fresh subprocess** (`era5bench.worker`). This keeps fsspec, xarray and HDF5 caches from leaking between repeats.
- Data prep (copies, uploads, ref generation) lives in `scripts/` and never runs as a side effect of benchmarking.
- Don't commit data, results or credentials. `data/` and `results/` are git-ignored.

## Layout
```
config/sites.yaml      Casper cases (paths/URLs, TODO markers)
config/local.yaml      Laptop smoke-test cases (local fixture + GCP)
src/era5bench/         config, openers, workloads, worker, runner, results
scripts/               prep_* data staging, make_local_fixture.py, run_casper.pbs, run_local.sh
tests/                 pytest on a tiny synthetic fixture (no network)
```

## Common commands
```bash
conda env create -f environment.yml && conda activate era5bench
pip install -e .
pytest -q
python scripts/make_local_fixture.py               # laptop: small ARCO slice -> data/local/
python -m era5bench.runner -c config/local.yaml --repeats 1
python -m era5bench.runner -c config/sites.yaml --cases zarr-lustre --workloads point_series
python -m era5bench.results results/<file>.csv     # summary table
```
