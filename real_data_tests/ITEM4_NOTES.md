# Item 4 — things noted for Jay, not attempted

Per the 26 October 2026 round's explicit instruction: these are
**noted only**. Nothing below was downloaded, installed, or
connected to this round.

## SatNOGS

Needs a free account and API key to use. Jay said he'll register
himself if this goes ahead — no account created, nothing attempted.

## ISS live telemetry (plan only, not attempted)

The ISS publishes live telemetry over a public Lightstreamer feed,
documented and consumed by the open-source **ISS Mimic** project
(a community-built physical/software model of the station that
reads this same feed). It has **no archive** — using it means
recording it live, there is no historical dataset to simply download.

**One-paragraph plan, for later, not built:** a small, separate
recorder script (outside `agents/`, likely `real_data_tests/iss_live/`
or similar) would connect to the Lightstreamer feed (following ISS
Mimic's own documented subscription channels/telemetry IDs as the
reference for what's available and how to parse it), write whatever
window of real telemetry it captures to a local, gitignored file with
a timestamp of when it was recorded (since, unlike every other
dataset in this project, this one can never be re-downloaded
identically — the capture window itself becomes the permanent
record), and that recording would then feed GRACIE in **ghost mode**
(the existing `agents/ghost_mode.py` pattern — watch real traffic,
compare against what the orchestrator would have decided, change
nothing real) rather than any live control path. Not started.

## ESPSS and Basilisk (noted only, not installed)

- **ESPSS** (ESA's propulsion system simulator) is licensed software
  — for ETHAN's world later. Not installed, no licence obtained or
  requested.
- **Basilisk** (open-source Python/C++ spacecraft simulation
  framework, University of Colorado Boulder AVS Lab) — for ETHAN
  and/or LUNAE's world later. Open-source and installable without an
  account, but not installed this round — noted only, per
  instruction.

## NASA Open MCT, GMAT, Trick (noted only, not installed)

- **NASA Open MCT** (open-source mission-control display framework,
  TypeScript/web-based) — for a later LEON mission-control dashboard,
  showing what the agents are doing fed from LEON's own outputs. Must
  sit entirely outside `agents/` if ever built, same as this whole
  session's discipline for anything that isn't core agent logic. Not
  installed.
- **NASA GMAT** (General Mission Analysis Tool, open-source
  trajectory/orbit determination software) — for LUNAE's world
  later. Not installed.
- **NASA Trick** (open-source simulation framework) — Jay's own
  instruction already flagged this as "probably not for this
  laptop" (heavy, mainly Linux-targeted). Not installed, not
  recommended for this machine without a strong reason to revisit
  that judgment.
