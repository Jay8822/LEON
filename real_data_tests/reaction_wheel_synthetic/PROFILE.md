# Reaction wheel fault dataset (SIMULATED) — profile

Item 4e of the 26 October 2026 round (`Ccode update.txt`). **Look
only.** Jay's instruction: "label clearly as simulated" — done
throughout. For LUNAE (navigation) later, not this round.

## SIMULATED — not real hardware, stated plainly, every time this is mentioned

"Synthetic Reaction Wheel Datasets for Nominal and Faulty
Conditions," published on Mendeley Data (not IEEE DataPort itself —
the IEEE DataPort listing found first, "Normal and Faulty Residual
Signals of Spacecraft Reaction Wheel," DOI 10.21227/jr1c-bm66, is
most likely the same underlying work's companion release, but its
own file sizes looked implausibly small (~200 bytes) when checked —
not pursued further; the Mendeley release, DOI 10.17632/rzxxk4sgg6.1,
is the one actually profiled here). Generated entirely in MATLAB
from Bialke's high-fidelity reaction wheel model, simulating a
satellite's reaction wheel under nominal operation and four fault
types: high bus voltage, low bus voltage, current losses, high
friction. Licence: CC BY-NC 3.0 (non-commercial use only — note this
if this dataset is ever used beyond research/educational purposes).

## Structure, confirmed from the dataset's own page description

Nine datasets total, in three groups of three (1-3, 4-6, 7-9), each
group describing the SAME underlying signals from a different
processing stage — matching cell indices across the three groups
correspond to the same simulated run:

- **MJAPF and SPF datasets:** each cell a 2×1001 array — row 1 is a
  categorical health-state label, row 2 is motor current (A) as
  estimated by one of two named filtering methods (MJAPF, SPF).
- **Raw datasets:** each cell a 5×1001 array — health-state label,
  SENSOR-MEASURED motor current (A, includes sensor noise),
  SENSOR-MEASURED angular velocity (rad/s, includes sensor noise),
  TRUE motor current (A, process noise only, no sensor noise), TRUE
  angular velocity (rad/s, process noise only). The measured-vs-true
  split is exactly the kind of structure a detection test would want
  — a known, labelled ground truth distinct from what a sensor would
  actually report.
- **Timing:** samples 0.1 s apart, ~100 seconds per series (1001
  samples).

## Honest limit: the actual files were not downloaded this round

The dataset's own landing page is reachable without an account, and
its licence and structure are both confirmed directly from that page
(not secondhand). But no working direct-download URL for the actual
MATLAB files was found this round using Mendeley's public API
endpoints tried — they returned unrelated search results, not this
specific dataset's file listing. This profile is built entirely from
the page's own detailed description, not from loading the data
itself. **This is a gap to close later, not a dead end** — the
dataset is real, licensed for this use, and well enough documented
to plan around; getting the actual files just needs more time than
this round allowed, or the IEEE DataPort companion checked more
carefully despite its odd file sizes.

## What this means for later rounds (not decided now)

The measured-vs-true structure is well suited to a detection-accuracy
test against a KNOWN ground truth, same spirit as `simulated_tests/
leash_drift/`'s own planted-fault design — but this data is already
simulated start to finish (no real hardware noise to bootstrap from),
so any future use should stay clearly labelled SIMULATED throughout,
same as this profile. For LUNAE specifically, per Jay's instruction.
Not decided or built this round.
