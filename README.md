# LEON — Autonomous Mission Governance Layer

A multi-agent software architecture for spacecraft fault management,
built as a learning/portfolio project and TRL 3 proof-of-concept — not
flight software, not validated, not ready to fly anything.

Independent agents monitor telemetry, escalate faults across subsystem
boundaries, and command safe states without ground-in-the-loop
response. Concept and architecture by Jay Pratt, built with AI
pair-programming assistance (Claude, Anthropic) — every substantive
change is attributed in commit history via `Co-Authored-By` trailers
and per-file "Updated" headers.

## What's actually here

Three separate, independently-runnable pieces, at three different
levels of maturity. None of them are flight software.

### 1. Python simulation (`agents/`, `core/`, `main.py`) — the main one

Six components communicating over a shared in-memory pub/sub event bus:

- **GRACIE** — health monitoring; evaluates telemetry, raises NOMINAL / WARNING / FAULT, latches FAULT until an explicit `clear_fault`
- **EDEN** — reacts to GRACIE's FAULT reports by commanding SAFE_MODE
- **ETHAN** — propulsion; responds to mode and safe-mode commands
- **LUNAE** — navigation state; switches to HOLD on FAULT
- **HALIA** — crew command interface (typed message validation via pydantic; plain, non-generative responses to a fixed set of recognized commands — "status," "run diagnostic on \<system\>," "help," etc.)
- **SystemCoordinator** — cross-subsystem status registry; alerts on the transition into FAULT

Also present but **not wired into the running app**: `Orchestrator`
(a scripted diagnostic sequencer, runnable on its own).

Run it:

    python main.py

Requires Python 3.10+. HALIA's message validation uses `pydantic`.

Tests (each runnable standalone — `python -m agents.<name>`):
`gracie_test`, `lunae_test`, `halia_test`, `test_halia_gracie`,
`test_message`, `orchestrator`.

### 2. C++ Power-of-10 test build (`AI Stack C++ Test Build/`)

A from-scratch redesign — not a port — of GRACIE, EDEN, and the
coordinator's fault-escalation chain, written to NASA/JPL's "Power of
10" rules for safety-critical C (no dynamic allocation, no function
pointers, fixed loop bounds, etc.). The no-function-pointers rule rules
out the Python version's pub/sub pattern entirely, so this uses a
statically-wired cyclic executive instead — see that folder's own
README for the full rationale.

Compiles clean with zero warnings on three separate toolchains (MinGW
GCC, MSVC, Clang) and passes its `ctest`/`cppcheck` targets — full
record in `AI Stack C++ Test Build/build.log`. Only covers
GRACIE/EDEN/coordinator; ETHAN, LUNAE, and HALIA have no C++
equivalent. Its schema is deliberately narrower than the Python
version's (documented in that folder's README) — that's an intentional
ground-simulation-vs-flight-representative-subset split, not drift.

Build it:

    cd "AI Stack C++ Test Build"
    cmake -S . -B build
    cmake --build build
    ctest --test-dir build

### 3. Standalone-process demonstrator (`distributed/`)

GRACIE and EDEN running as two genuinely separate OS processes,
talking over a raw TCP socket (newline-delimited JSON) instead of
sharing an in-memory bus — proof that the agent classes are actually
independent modules, not just decoupled objects inside one process.
Uses the real, unmodified `agents.gracie.GracieAgent` and
`agents.eden.EdenAgent` classes. See `distributed/README.md` for why
raw sockets rather than DDS or ZeroMQ (what a real distributed build
would use), and what extending this to the other agents would take.

Run it (two terminals, from the repo root):

    python -m distributed.eden_process      # terminal 1, start this first
    python -m distributed.gracie_process     # terminal 2

## Status

TRL 3 — experimental proof of concept. The Python simulation
demonstrates the core fault-escalation logic (FAULT latching,
cross-subsystem alerting) on synthetic telemetry; the C++ build
demonstrates the same logic written to a safety-critical coding
standard; the distributed demonstrator shows two of six components as
genuinely separate processes. None of this has been verified,
validated, or reviewed against real flight-software standards beyond
static analysis and unit-level checks — interested in V&V feedback to
understand what that would actually take, not claiming to be there.

## Known limitations

- Only 2 of 6 components run as separate processes; the rest still
  share one in-process bus.
- HALIA recognizes a fixed set of commands; anything else gets a
  plain "unrecognized command" response, not a generated one.
- The C++ build covers 3 of 6 components and has a deliberately
  narrower schema than the Python version.
- All telemetry is synthetic (randomized or fixed test sequences), not
  from any real sensor.

## Provenance

Concept and architecture by James "Jay" Pratt. Built with AI
pair-programming assistance (Claude, Anthropic) throughout — see
commit history (`Co-Authored-By` trailers) and per-file "Updated"
headers for exactly what changed when. Originally prototyped November
2025; a substantial correctness pass, the C++ port, and this README
followed in July 2026.
