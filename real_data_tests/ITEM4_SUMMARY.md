# Item 4 — overall summary (26 October 2026 round)

Look-only round: download and profile, no scoring/testing code
built against any of these. Full detail in each dataset's own
`PROFILE.md`; noted-only items (not attempted) in `ITEM4_NOTES.md`.

## What was gotten vs. not, and why

| Dataset | Status | Why |
|---|---|---|
| a) NASA ADAPT | Documentation only — companion paper downloaded and read in full; the actual dataset files are unreachable (NASA DASHlink host times out) | Same host outage as the battery dataset |
| b) Li-ion Battery Aging | **Skipped entirely, on hold per Jay's standing instruction** | Already-known DASHlink/account obstacle from the simulated-craft round |
| b) BP930 Small Satellite Power Simulation | Downloaded and profiled in full | Hosted on `data.nasa.gov` directly, not DASHlink — reachable |
| c) ESA Mars Express Power Challenge | Downloaded and profiled in full, MD5-verified | Hosted on Zenodo — reachable |
| d) Rosetta reaction wheel (PDS) | Small sample downloaded and profiled (2 of 5 parameters, 1 of 4 wheels, 1 of ~48 quarters) | Reachable; full ~1.6 GB bundle not needed for a profile |
| e) IEEE DataPort / Mendeley reaction wheel (simulated) | Profiled from the dataset's own page description; actual files NOT downloaded | No working direct-download URL found via Mendeley's public API this round |
| f) Express-A2/A3 Hall thruster (NTRS) | One representative part (of 12) downloaded and profiled in full | Reachable (`ntrs.nasa.gov`, not DASHlink) |
| g) C-MAPSS turbofan (addendum) | FD001 downloaded and profiled via a verified non-NASA mirror | NASA's own DASHlink host unreachable; a wrong, much larger dataset (N-CMAPSS, 15.7 GB) was found and correctly rejected first |

## The one answer Jay most wanted: can ADAPT's documentation support a real blueprint?

**Yes, more than any other dataset in this project so far** — three
things line up: (1) an explicit sensor-to-component schematic: every
sensor is tied to a named physical component, not just a channel
number; (2) commands and their expected sensor effect are recorded
together with real timing, in the data format itself (a documented
example: a relay-open command followed by its own feedback sensor
confirming open, with the exact delay) — closer to SPEC.md's
"expected kicks" than anything hand-built in this project before; (3)
ground truth is at the COMPONENT level (a true vs. predicted
"component mode vector," scored by Hamming distance) — which is
exactly why ADAPT's own benchmarking literature already tests BOTH
detection AND isolation, unlike ESA-ADB/OPS-SAT which only ever
support detection. **Caveat, stated plainly: this is a
documentation-based answer, not a verified one** — the raw data
files that would let this project actually build and test a
blueprint from ADAPT remain unreachable from this machine.

## A recurring finding across this round: NASA's DASHlink host (`c3.nasa.gov` / `c3.ndc.nasa.gov`) is down, not individual broken links

Confirmed independently, repeatedly, across completely different
datasets (ADAPT's five files, the Li-ion battery dataset from the
earlier round, C-MAPSS) and different URL paths on that same host —
every attempt times out, cleanly and consistently. This is
infrastructure, not a one-off dead link; worth periodically
re-checking in a later round rather than assumed permanent, but not
chased further by creating accounts on paid/gated mirrors, per the
standing "never create an account" rule.

## Disk and memory

~190 MB total downloaded across every dataset this round (largest:
Mars Express Power, 147 MB), well within the 101 GB free on this
disk. No full dataset was ever loaded whole into memory — the three
~600 MB Mars Express power-channel files were profiled by streaming
rows directly from the zip, never extracted or loaded in full, given
this machine's 6 GB RAM.

## What wasn't done (explicitly, not forgotten)

- No scoring/testing code was built against any of these datasets —
  that's a separate, later round, with ambiguities first, same as
  every other dataset decision this session.
- The Li-ion battery dataset is still on hold — Jay's call whether to
  chase it further.
- ADAPT's and IEEE DataPort/Mendeley's actual data files weren't
  obtained — documentation-based profiles only for those two.
- The "note only" items (SatNOGS, ISS live telemetry, ESPSS,
  Basilisk, Open MCT, GMAT, Trick) — nothing attempted, see
  `ITEM4_NOTES.md`.
