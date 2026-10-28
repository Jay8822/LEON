# ADAPT (Advanced Diagnostics and Prognostics Testbed) — profile

Item 4a of the 26 October 2026 round (`Ccode update.txt`). **Look
only — download and profile, no scoring/testing code built this
round.**

## What it actually is

A real hardware Electrical Power System (EPS) testbed at NASA Ames,
built from commercial off-the-shelf parts in a topology that mimics
a real spacecraft EPS: battery chargers (energy conversion), three
sets of lead-acid batteries (energy storage), two inverters plus
relays/circuit breakers/loads (power distribution), and a data
acquisition/control system (power management). It delivers both AC
and DC power to loads standing in for avionics, propulsion, life
support, environmental control and science-payload subsystems.

Two configurations exist: the full **ADAPT** (173 components, 430
component modes) and a simpler **ADAPT-Lite** subset (37 components,
93 modes) used for easier benchmarking runs.

## Sensors

Measured quantities: voltage, current, temperature, phase angle, and
switch/relay position (open/closed feedback). Sensors are named by
location in the EPS schematic — e.g. `IT240` (battery 2's current),
`ST516` (a fan speed sensor), `E261` (the downstream voltage of relay
`EY260`), `ESH275` (the position-feedback sensor for relay `EY275`).
Sampling is 2 Hz, roughly four minutes per scenario (30s startup, 3
minutes of fault/nominal window, 30s shutdown).

## Fault catalog (component → fault type), straight from the benchmarking paper

| Component | Fault |
|---|---|
| Battery | Degraded |
| Boolean Sensor | Stuck at Value |
| Circuit Breaker | Failed Open, Stuck Closed |
| Inverter | Failed Off |
| Relay | Stuck Open, Stuck Closed |
| Sensor | Stuck at Value, Offset |
| Pump (load) | Flow Blocked, Failed Off |
| Fan (load) | Over Speed, Under Speed, Failed Off |
| Light Bulb (load) | Failed Off |
| Basic Load | Failed Off |

Faults are injected three ways: **hardware-induced** (physically
tripping a breaker or switch), **software-injected** (blocking
commands sent to the testbed, or altering the sensor data an
"antagonist" process reports — exactly what Jay's instruction
described), and (not used in the benchmarking study) genuinely faulty
real components. Scenarios include single faults and, in full ADAPT
only, double- and triple-fault combinations — roughly a third of
ADAPT's scenarios are nominal (no fault), the rest split across
single/double/triple.

## Does the documentation support a real blueprint? Jay's main question — yes, more than any other dataset in this project so far

Three things point the same way:

1. **An explicit sensor-to-component schematic exists** (the EPS
   diagram, `AdaptHTMLdiagrams.zip` — not downloadable this round,
   see below, but its existence and content are confirmed by the
   benchmarking paper, which reproduces it). Every sensor is tied to
   a named component it measures, not just a channel number.
2. **Commands and their expected sensor effect are recorded
   together, with real timing**, directly in the data format. The
   paper quotes an actual data excerpt:
   ```
   command @120950 EY275CL = false;
   sensors @121001 {...ESH275 = true, ...}
   sensors @121501 {...ESH275 = false, ...}
   ```
   A command opens relay `EY275`; its own feedback sensor `ESH275`
   is expected to reflect that within a short, bounded delay. This is
   a REAL, documented command→expected-sensor-effect relationship —
   closer to SPEC.md's "expected kicks" concept than anything this
   project has built a blueprint from before (the simulated craft had
   to invent this relationship by hand; ESA-ADB's `expected_causes`
   only ever had a statistical command/event correlation to go on,
   never a stated, guaranteed causal link).
3. **Ground truth is at the COMPONENT level, not just the sensor
   level** — a "true component mode vector" vs. the diagnostic
   algorithm's "predicted component mode vector," scored by Hamming
   distance. This is why ADAPT uniquely supports testing **both
   detection AND isolation** (Jay's specific question) — every other
   real dataset this project has used (ESA-ADB, OPS-SAT) only ever
   supported detection scoring, because they label WHEN something is
   wrong, not WHICH named component is the true cause.

**Caveat, stated plainly: this is a documentation-based assessment,
not a verified one.** The raw data files that would actually let this
project build and test a blueprint from ADAPT could not be downloaded
this round — see below.

## Honest limit: the actual dataset files are unreachable from this machine

Checked directly, repeatedly, on several different paths (not one
broken link): NASA's DASHlink host (`c3.nasa.gov` / `c3.ndc.nasa.gov`,
which serves ADAPT's five primary files — the PDF documentation, the
HTML diagrams, the experiment log, and the two dataset archives) times
out on every connection attempt from this machine. **This is the
exact same obstacle already found and reported for the NASA Li-ion
Battery Aging dataset** (on hold per Jay's own instruction) — the
same NASA file-hosting infrastructure, not two separate problems.
`real_data_tests/adapt/download_adapt.py` lists and attempts all five
files anyway (cheap to retry; it will work automatically if that host
comes back up) but none succeeded this round.

What WAS reachable: `ntrs.nasa.gov` (a different NASA host, for
technical reports, not DASHlink's file server) served the companion
benchmarking paper's PDF cleanly — `Kurtoglu et al., "Benchmarking
Diagnostic Algorithms on an Electrical Power System Testbed,"
PHM Society Annual Conference, 2009` (NTRS doc ID 20110011109,
7,823,525 bytes, downloaded via `download_adapt.py`). This whole
profile is built from that paper, not from the raw dataset.

## The related Diagnostic Challenge (DXC) data

The DXC competition (`DXC'09 Industrial Track Sample Data`, also
listed on data.gov, and the "ADAPT EPS Benchmarking" framework the
paper describes) reuses the same ADAPT hardware and fault catalog for
a diagnosis competition format. Its sample data is also hosted on the
same DASHlink infrastructure and was not independently checked this
round — given the primary host is confirmed unreachable, it's a safe
assumption the DXC files share the same fate, not separately verified.

## Licence

Listed as public on data.gov / catalog.data.gov; one catalog mirror
states no explicit licence text is provided. Treat as a US government
public-domain technical work (the normal default for NASA technical
data) but note the absence of an explicit licence statement if this
is ever cited formally.

## What this means for later rounds (not decided now)

If NASA's DASHlink host becomes reachable (worth periodically
re-checking — this is infrastructure, not a permanent takedown, as
far as could be determined), ADAPT is the strongest candidate so far
for an isolation-scoring real-data test, and for deriving a blueprint
from real documentation rather than a hand-built one. Any actual test
plan against it is a separate, later round, ambiguities first, same
as every other dataset decision this session.
