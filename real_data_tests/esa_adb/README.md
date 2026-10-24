# ESA-ADB (ESA Anomaly Dataset) — download only, for now

Third real-data test planned for LEON (SPEC.md's "Real-data testing"
section: "Three public, labelled datasets, in order: ESA OPS-SAT
(OPSSAT-AD), NASA SMAP/MSL, then ESA-ADB"). This folder currently only
downloads the dataset — no profiling, unpacking, or testing yet. That
comes later, deliberately in small chunks: SPEC.md flags this dataset
as large, and the laptop has 6 GB of memory.

## Dataset

De Canio, G., Kotowski, K. & Haskamp, C., with Andrzejewski, J.,
Ruszczak, B., Nalepa, J., Lakey, D., Collins, P., Kolmas, A.,
Bartesaghi, M. & Martinez-Heras, J. "ESA Anomaly Dataset" (2024).
https://doi.org/10.5281/zenodo.12528696

Companion paper: Kotowski et al., "European Space Agency Benchmark for
Anomaly Detection in Satellite Telemetry," arXiv:2406.17826 (2024).

Licence: CC BY 3.0 IGO.

Only Missions 1 and 2 (one zip archive each, 7.9 GB total) — the two
the ESA-ADB benchmark actually uses. Mission1 has 76 telemetry
channels (58 monitored for anomalies), Mission2 has 100 (47
monitored). The dataset's Mission3 is deliberately not downloaded
here: per the benchmark paper it has few, trivial anomalies and many
communication gaps, and isn't part of the benchmark at all.

## Running it

Raw data is never committed to this repo — `data/` here is gitignored.
This step only downloads; it does not unpack or load anything:

    python -m real_data_tests.esa_adb.download_esa_adb

Each file is streamed straight to disk in 8 MB chunks, never held
whole in memory — two ~4 GB downloads on a 6 GB machine would be
risky otherwise, before any actual analysis even starts. Expect this
to take a long time; it's meant to run in the background.

## Honest limits

- Download only, right now. Profiling, unpacking and any detection
  test against this data are separate, later work, and will need to
  read it in chunks (one mission, a handful of channels at a time) —
  not loaded whole, per SPEC.md's own caution.
- Total size (7.9 GB for Missions 1 and 2) is the Zenodo record's own
  figure, checked directly — some secondary sources claimed 31 GB for
  all three missions combined; the record itself is authoritative and
  is what the download script and MD5s are built against.
