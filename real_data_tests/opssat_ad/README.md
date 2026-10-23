# OPSSAT-AD real-data test

First real-data test for LEON (HANDOVER.md task 4, SPEC.md's "Real-data
testing" section). Tests the single-reading, threshold-based detection
*approach* GRACIE uses — not GRACIE's own code. GRACIE's real FAULT
logic needs two channels at once (temperature AND radiation);
OPSSAT-AD's labelled fragments are each a single channel in isolation,
so that two-field condition can't be exercised from this data at all.
See `run_opssat_ad_test.py`'s module docstring for the full design and
every interpretive call made.

**First test against real spacecraft data. Not a validation.**

## Dataset

Ruszczak, B., Kotowski, K., Nalepa, J. & Evans, D. "OPSSAT-AD —
anomaly detection dataset for satellite telemetry" (2024).
https://doi.org/10.5281/zenodo.12588359

Companion paper: Ruszczak, Kotowski, Nalepa & Evans, "The OPS-SAT
benchmark for detecting anomalies in satellite telemetry,"
arXiv:2407.04730 (2024).

Licence: CC-BY-4.0.

2,123 single-channel telemetry fragments across 9 real OPS-SAT
channels (3 magnetometer, 6 photodiode), each labelled nominal or
anomalous, with a provided train/test split.

## Running it

Raw data is never committed to this repo — `data/` here is gitignored.

    python -m real_data_tests.opssat_ad.download_opssat_ad
    python -m real_data_tests.opssat_ad.run_opssat_ad_test

## Honest limits

- None of the 9 channels are temperature or radiation. No channel is
  relabelled as one; results are reported per real channel name.
- Thresholds (level and jump) are derived statistically from this
  dataset's own training split, fixed before any test-split result is
  looked at — not GRACIE's real numbers, not hardware-calibrated.
- "Spike vs. drift" characterisation of missed anomalies is a manual
  heuristic in the script, not a label the dataset provides.
- The rate-of-change jump check's cross-check half (SPEC.md's
  "Rate-of-change sense" section) is untested here, by construction:
  every fragment is a single channel in isolation, so there's nothing
  else to corroborate a jump against. Every jump-check hit on this
  dataset can only ever be "logged," never "flagged." The cross-check
  itself is expected to be tested later against ESA-ADB, which records
  multiple channels at the same time.
