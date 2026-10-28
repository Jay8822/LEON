# Express-A2/A3 Hall-effect thruster telemetry — profile

Item 4f of the 26 October 2026 round (`Ccode update.txt`). **Look
only — downloaded and profiled, no scoring/testing code built this
round.** For ETHAN (propulsion) later, per Jay's instruction, not
acted on now.

## What it is

A 12-part NASA Glenn contractor report series (NASA/CR-2003-212005),
documenting real flight telemetry from the Hall-effect (SPT-100)
stationkeeping thrusters on two Russian GEO communications
satellites, Express-A2 and Express-A3 (launched March and June 2000
respectively), covering March 2000 to September 2001. Published on
NASA's Technical Reports Server. Distribution statement:
"Unclassified-Unlimited" — a US government technical report, no
further licence restriction stated. Only Part 3 (Express-A3 SPT-100
propulsion telemetry, June–September 2000, document ID 20030064312,
3,558,067 bytes) was downloaded and profiled this round; the other 11
parts follow the same NTRS citation pattern.

## Jay's specific question, answered directly: these ARE real, usable data tables, not just illustrative figures

Confirmed by extracting the PDF's own text (not by reading a
description of it) — the report's main body (pages ~1–40) contains
narrative description plus small discrete-event tables (e.g. Table
16/17: total firing durations and firing dates per thruster/cathode).
The actual telemetry — the part Jay's question was really about — is
in numbered Annexes starting around page 100, one per real firing
event, each a genuine column-structured table that extracts cleanly:

```
Time,        Cathode Current, Anode Current, Anode Voltage, Xe Feed Unit Output
hh:mm:ss     A                A              V              (kgf/sm2)
21:47:31     0,00             4,65           308            2,66
...
11:42:43     12,10            0,00           322            2,84   <- thruster ignites here
```

That ignition moment is directly visible in the raw extracted text
(Annex 10, Express-A3, 23/08/00): cathode current sits at exactly
`0,00` for several consecutive readings, then jumps to `12,10` A at
`11:42:43` while anode current drops to `0,00` at the same instant —
a real, observable state transition in the actual numbers, not
something inferred from a caption. Values use a European comma
decimal (`0,00` = 0.00) and samples are irregular, roughly every
5–30 seconds during active readings, becoming regular 30-second
samples during some stretches (e.g. page 171) — both patterns
confirmed directly in different Annexes of the same Part.

## What's actually in the telemetry tables

Four real measured columns per firing event: cathode current (A),
anode current (A), anode voltage (V), and Xenon Feed Unit output
pressure (kgf/cm²) — plus a free-text "Comments" column. Table
16/17 in the main body separately give each thruster/cathode's total
firing duration and the exact date/time of every firing in the
reporting period, which is the natural index into which Annex covers
which firing.

## Honest limits

- Text extraction used Python's `pdfplumber`, not a human reading the
  PDF — spot-checked on several pages (100, 110, 120, 130, 140, 150,
  160, 170, 180, 190) and all showed clean, well-formed numeric
  tables, but not every one of this Part's ~90 annex pages was
  checked individually, and the other 11 parts of the series weren't
  opened at all this round.
- Comma-decimal formatting (`0,00`) would need conversion before any
  numeric use — a small but real parsing step.
- Only four measured quantities (current ×2, voltage, pressure) —
  far fewer sensors than ADAPT or the simulated craft's engine
  subsystem; this dataset is narrow but deep (real ignition
  transients, not a broad multi-sensor system).

## What this means for later rounds (not decided now)

The first real candidate this project has for ETHAN (propulsion)
specifically, with a genuine, directly-observed ignition transient in
the raw data — plausibly useful for testing "expected kicks" around
a real commanded firing, the same spirit as the Mars Express
dataset's DMOP commands but for a thruster instead of a power
subsystem. Any actual test plan is a separate, later round,
ambiguities first, same as every other dataset decision this session.
