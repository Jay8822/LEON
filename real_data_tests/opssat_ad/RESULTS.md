# OPSSAT-AD test results

**First real-data test for LEON. Not a validation.** Threshold-based
detection *approach* only — not GRACIE's own code; see `README.md`
for exactly why (OPSSAT-AD's fragments are single-channel, GRACIE's
real FAULT logic needs two channels at once) and for every other
interpretive call and honest limit, which this page doesn't repeat.

## Dataset

2,123 fragments across 9 real OPS-SAT channels (3 magnetometer —
CADC0872/0873/0874; 6 photodiode — CADC0884/0886/0888/0890/0892/0894),
provided train/test split: 1,594 train, **529 test** — the same 529
test fragments the C++ GRACIE core's cross-language proof runs
against (`real_data_tests/cpp_proof/`), bit-exact on every one of
them.

Two settings, both derived from each channel's own nominal training
fragments, fixed before any test-split result was looked at:
**STRICT** (95th/5th percentile) and **LOOSE** (99th/1st percentile).

## STRICT (95th/5th percentile)

### Level only

| Channel | Caught | Missed | False alarm | Quiet |
|---|---|---|---|---|
| CADC0872 | 9 | 23 | 8 | 92 |
| CADC0873 | 8 | 23 | 8 | 114 |
| CADC0874 | 2 | 21 | 2 | 27 |
| CADC0884 | 0 | 0 | 2 | 34 |
| CADC0886 | 0 | 1 | 0 | 3 |
| CADC0888 | 1 | 11 | 1 | 51 |
| CADC0890 | 0 | 2 | 0 | 0 |
| CADC0892 | 0 | 7 | 1 | 45 |
| CADC0894 | 0 | 5 | 0 | 28 |
| **TOTAL** | **20** | **93** | **22** | **394** |

20/113 anomalous fragments caught = **17.7%** (~18%). Missed,
manually characterised by shape (heuristic, not a dataset label):
40 spike-like, 53 drift-like.

### Level + jump

Jump-check hits here are logged only, never flagged (the cross-check
needs a second channel, which single-channel fragments don't have —
see `README.md`).

| Channel | Caught (either) | level only | jump only | both | Missed (both) | False alarm (level) | False log (jump) |
|---|---|---|---|---|---|---|---|
| CADC0872 | 24 | 0 | 15 | 9 | 8 | 8 | 1 |
| CADC0873 | 29 | 0 | 21 | 8 | 2 | 8 | 5 |
| CADC0874 | 22 | 0 | 20 | 2 | 1 | 2 | 0 |
| CADC0884 | 0 | 0 | 0 | 0 | 0 | 2 | 4 |
| CADC0886 | 0 | 0 | 0 | 0 | 1 | 0 | 1 |
| CADC0888 | 10 | 0 | 9 | 1 | 2 | 1 | 3 |
| CADC0890 | 2 | 0 | 2 | 0 | 0 | 0 | 0 |
| CADC0892 | 0 | 0 | 0 | 0 | 7 | 1 | 0 |
| CADC0894 | 1 | 0 | 1 | 0 | 4 | 0 | 1 |
| **TOTAL** | **88** | **0** | **68** | **20** | **25** | **22** | **15** |

88/113 = **77.9%** (~78%) — up from level-only's 17.7%. Of the
fragments level alone missed: jump catches 36/40 spike-like ones and
32/53 drift-like ones.

## LOOSE (99th/1st percentile)

### Level only

| Channel | Caught | Missed | False alarm | Quiet |
|---|---|---|---|---|
| CADC0872 | 8 | 24 | 1 | 99 |
| CADC0873 | 6 | 25 | 3 | 119 |
| CADC0874 | 2 | 21 | 0 | 29 |
| CADC0884 | 0 | 0 | 1 | 35 |
| CADC0886 | 0 | 1 | 0 | 3 |
| CADC0888 | 0 | 12 | 1 | 51 |
| CADC0890 | 0 | 2 | 0 | 0 |
| CADC0892 | 0 | 7 | 1 | 45 |
| CADC0894 | 0 | 5 | 0 | 28 |
| **TOTAL** | **16** | **97** | **7** | **409** |

16/113 = 14.2%. Missed, characterised: 41 spike-like, 56 drift-like.

### Level + jump

| Channel | Caught (either) | level only | jump only | both | Missed (both) | False alarm (level) | False log (jump) |
|---|---|---|---|---|---|---|---|
| CADC0872 | 23 | 1 | 15 | 7 | 9 | 1 | 0 |
| CADC0873 | 25 | 0 | 19 | 6 | 6 | 3 | 2 |
| CADC0874 | 22 | 0 | 20 | 2 | 1 | 0 | 0 |
| CADC0884 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| CADC0886 | 0 | 0 | 0 | 0 | 1 | 0 | 1 |
| CADC0888 | 9 | 0 | 9 | 0 | 3 | 1 | 1 |
| CADC0890 | 2 | 0 | 2 | 0 | 0 | 0 | 0 |
| CADC0892 | 0 | 0 | 0 | 0 | 7 | 1 | 0 |
| CADC0894 | 0 | 0 | 0 | 0 | 5 | 0 | 0 |
| **TOTAL** | **81** | **1** | **65** | **15** | **32** | **7** | **4** |

81/113 = 71.7% — up from level-only's 14.2%. Of the fragments level
alone missed: jump catches 32/41 spike-like ones and 33/56
drift-like ones.

## Plain summary

Jump adds a large amount of coverage on top of level alone, at both
settings — roughly 4x more fragments caught overall (STRICT:
17.7%→77.9%; LOOSE: 14.2%→71.7%). Almost all of that gain is
**jump-only** (STRICT: 68 of 88; LOOSE: 65 of 81) — level and jump are
catching largely different fragments, not mostly overlapping on the
same ones. Every jump-check hit here is a LOGGED event, never a
FLAGGED one (see above) — this scorecard counts "did either sense
notice," not "did either sense raise the ship's alarm level."

Leash (sustained drift) is not included above: it registers zero
pulls anywhere in this dataset, at any setting, train or test,
nominal or anomalous — see `README.md`'s own honest-limits section
for why (OPS-SAT's fragments are mostly too short or too spike-shaped
for a sense tuned to sustained drift) and `simulated_tests/leash_drift/`
for a controlled test of the mechanism itself.

## Honest limits

See `README.md` — not repeated here. In particular: this is the
threshold-based detection *approach*, not GRACIE's own code; neither
channel type is temperature or radiation; thresholds are derived
statistically from this dataset's own training split, not GRACIE's
real numbers; "spike vs. drift" is a manual heuristic, not a dataset
label; the jump cross-check and leash's context-gating are both
untested here by construction (single-channel fragments have nothing
to corroborate against).
