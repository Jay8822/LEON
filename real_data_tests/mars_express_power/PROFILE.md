# ESA Mars Express Power Challenge — profile

Item 4c of the 26 October 2026 round (`Ccode update.txt`). **Look
only — downloaded and profiled, no scoring/testing code built this
round.** Verified by MD5 against Zenodo's own published checksum
after download (`download_mars_express_power.py`).

## What it is

Real telemetry from ESA's Mars Express orbiter, published for a 2016
Kelvins competition: predict the spacecraft's thermal power
consumption for an upcoming Martian year from its past telemetry and
known future plans. **Three full Martian years of training data**
(2008-08-22 to 2014-04-14) plus a fourth year of context-only test
data (2014-04-14 to 2016-03-01, no power readings — they're what the
competition asked entrants to predict).

## Sensor data: 33 thermal power lines, no anomaly labels

One `power--<start>_<end>.csv` file per training year (591–618 MB
each, ~1.8 GB combined uncompressed — too large to load whole on this
6 GB machine; profiled by streaming the first few rows and by
spot-checking further in, not by loading a full year into memory).
34 columns: `ut_ms` (Unix ms timestamp) plus 33 `NPWD####` columns —
electric current measurements for 33 named thermal power lines, at
roughly 30–60 second intervals. **No fault or anomaly labels at all**
— confirmed, matches what Jay's instruction already said. This is a
regression/prediction dataset, not a labelled-fault one.

## Context data: exactly what's needed for "expected kicks" and ageing

Four context file types, one set per training year plus one for the
test year, all plain CSV:

- **DMOP** (`context--...--dmop.csv`, 3.7–4.9 MB/year): `ut_ms`,
  `subsystem` — a command code (e.g. `AXXX301A`, `AAAAF20C1`) for a
  real subsystem action. **This is a real command log with real
  timing**, the same kind of thing ESA-ADB's telecommand correlation
  and the simulated craft's hand-built event schedule both had to
  work with or invent — here it's native to the dataset.
- **SAAF** (3-byte angles, 27–48 MB/year, by far the largest context
  file — sampled much more densely than the others): `ut_ms`, `sa`
  (solar panel normal angle — directly indicates power received),
  `sx`/`sy`/`sz` (satellite axis angles relative to the Sun-Mars
  Express line).
- **FTL** (0.5–0.9 MB/year): `utb_ms`/`ute_ms` (a pointing period's
  start/end), `type` (e.g. `"EARTH"` — what the spacecraft is
  pointing at), `flagcomms` (whether a comms device was active).
  Confirmed by direct inspection: periods are contiguous and
  non-overlapping, a clean start/end timeline.
- **EVTF** (3.0–3.6 MB/year): `ut_ms`, `description`. Confirmed by
  direct inspection (not just the page's own description): real
  eclipse events exist, with matched start/end pairs — e.g.
  `MAR_PENUMBRA_START` / `MAR_UMBRA_START` / `MAR_UMBRA_END` /
  `MAR_PENUMBRA_END` occurring together, 3,850 such lines found in
  just the first training year's file. This is the Mars-orbit
  equivalent of SPEC.md's own Blueprint example ("sensors that
  legitimately read zero in some conditions, for example light
  sensors in Earth's shadow") — with real, precise timing.
- **LTDATA** (~65 KB/year, one row per day): `ut_ms`, `sunmars_km`,
  `earthmars_km`, `sunmarsearthangle_deg`, `solarconstantmars` (W/m²
  at Mars — directly explains why available power varies over a
  Martian year), `eclipseduration_min`, `occultationduration_min`.

## For "expected kicks" (Jay's first specific question): yes, directly

DMOP's subsystem commands and FTL's pointing-period starts are both
real, precisely-timed triggers that should produce a predictable
reaction in the 33 power lines shortly after — the same shape of
relationship as the simulated craft's hand-built "engine burn →
engine-bay temperature kick," except here the trigger-and-reaction
pair is REAL, not designed in. EVTF's eclipse events are an even
cleaner case: an eclipse should produce an expected, bounded DIP in
solar-dependent power lines, with known start and end. This dataset
is well suited to testing SPEC.md's "expected kicks" concept against
real triggers and real reactions — not attempted this round (profile
only, per instruction).

## For ageing (Jay's second specific question): yes, three full years is enough to show it

LTDATA's `solarconstantmars` column means available solar power has
a real, known, physically-explained LONG-TERM variation (Mars's
elliptical orbit) that any ageing/drift analysis would need to
account for BEFORE attributing a power-line's slow change to
component ageing rather than orbital distance — a genuine, useful
complication this dataset forces a real ageing test to handle
properly, that the simulated craft's synthetic/random-walk ageing
story never had to. Three Martian years (compared to roughly one
year of ESA-ADB/OPS-SAT coverage) is also simply a longer baseline to
measure real long-term drift against.

## Honest limits

- No anomaly/fault labels at all — any future test against this data
  can only ever be a prediction/consistency exercise (does the power
  draw after a command/eclipse match what the context data implies
  it should?), never a detection-accuracy scorecard the way ESA-ADB's
  labelled anomalies are.
- Units for the 33 `NPWD` columns and the SAAF angles are not stated
  anywhere on the Kelvins page or in the files' own headers — treat
  any future numeric derivation from these as unitless/relative
  unless a clearer source is found.
- Not independently checked this round: the exact subsystem each
  `NPWD####` line number corresponds to, or what each DMOP subsystem
  code actually does physically. The Kelvins discussion page/forum
  (now archived, not fetched this round) may have more detail if a
  real test against this data is ever planned.

## What this means for later rounds (not decided now)

A genuinely strong candidate for testing "expected kicks" against
real triggers (DMOP commands, FTL pointing changes, EVTF eclipses)
and for a real multi-year ageing test — both explicitly flagged by
Jay as what this dataset is for. Any actual test plan is a separate,
later round, ambiguities first, same as every other dataset decision
this session.
