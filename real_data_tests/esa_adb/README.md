# ESA-ADB (ESA Anomaly Dataset)

Third real-data test for LEON (SPEC.md's "Real-data testing" section:
"Three public, labelled datasets, in order: ESA OPS-SAT (OPSSAT-AD),
NASA SMAP/MSL, then ESA-ADB"). Unlike OPSSAT-AD's separate batch
script, this test runs through the REAL GracieAgent
(`agents/gracie.py`, any-sensor rule book) via `process_readings()`,
one real sample at a time, in chronological order.

**First test against real spacecraft data. Not a validation.**

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

Raw data is never committed to this repo — `data/` and `results/` here
are both gitignored.

    python -m real_data_tests.esa_adb.download_esa_adb
    python -m real_data_tests.esa_adb.run_esa_adb_test

Each download is streamed straight to disk in 8 MB chunks, never held
whole in memory. The test itself processes one channel completely
(both settings) before checkpointing its result to
`results/<mission>.json` and moving to the next — never more than one
channel's full series in memory, and a re-run skips channels already
checkpointed, so an interrupted run resumes instead of restarting.
Both steps are slow by design; expect them to run in the background,
realistically overnight for the test.

## Method

- 8 monitored channels per mission, chosen by a fixed rule before any
  scoring (stratified across subsystems, fixed random seed) — never
  cherry-picked. The exact channels are printed and stored in the
  results file.
- One shared calendar cutoff date per mission (70% of that mission's
  own span), not a per-channel split — channels run concurrently and
  events span many of them, so a shared date keeps every event wholly
  on one side.
- Thresholds (level, jump, leash) are derived from the training
  period's NOMINAL-only data, chunked into 1-day pseudo-fragments
  (this dataset has no natural fragment boundaries), fixed before any
  test-period result is looked at. Two settings, STRICT and LOOSE,
  same convention as OPSSAT-AD.
- Anomalies and Rare Events are scored separately and reported
  honestly — see `run_esa_adb_test.py`'s module docstring, point 4,
  for why GRACIE's current senses can't actually tell them apart.
- `clear_fault()` is called at every calendar-day boundary in the test
  period, as a stand-in for a real sign-off (otherwise one early latch
  would stay latched for the rest of a multi-year recording and wreck
  the scoring) — see that same docstring, point 7, for an honest
  caveat this surfaced about the leash pull-duration clock.

## Honest limits

- First test, not a validation, same framing as OPSSAT-AD.
- Jump's cross-check and leash's context-gating are not implemented
  in GracieAgent at all yet, so neither is tested here regardless of
  what this dataset offers (and it offers a lot: labels.csv's
  multivariate events and telecommands.csv/events.csv are exactly the
  right shape for both, once built).
- Leash window/duration (1 hour / 6 hours / 24 hours) are fresh,
  labelled choices for this dataset's much longer timescale — not
  OPSSAT-AD's numbers, not hardware-calibrated.
- Total size (7.9 GB for Missions 1 and 2) is the Zenodo record's own
  figure, checked directly — some secondary sources claimed 31 GB for
  all three missions combined; the record itself is authoritative and
  is what the download script and MD5s are built against.
