# AI Stack
Full Ai Stack

# LEON — Autonomous Mission Governance Layer

A multi-agent software architecture for spacecraft fault management.
Independent agents monitor telemetry, escalate faults across subsystem
boundaries, and command safe states without ground-in-the-loop response.

## What it does

Five agents communicate over a shared event bus using typed message schemas:

- **GRACIE** — health monitoring; evaluates telemetry, raises NOMINAL / WARNING / FAULT
- **EDEN** — mission director; receives health events, issues safe-mode commands
- **ETHAN** — propulsion control; responds to mode and safe-mode commands
- **LUNAE** — navigation state
- **HALIA** — crew command interface
- **SystemCoordinator** — cross-subsystem status registry

When GRACIE detects a fault, EDEN independently commands a safe state.
The fault latches — it holds until an explicit operator `clear_fault`,
rather than resetting when telemetry momentarily recovers. Every decision,
its cause and its outcome is written to a per-agent audit log.

## Status

TRL 3 — experimental proof of concept, tested on synthetic telemetry.
Fault-escalation and three-tier health state demonstrated in logged runs
(see `/logs`). Developed independently with AI assistance; seeking
verification and validation partners to progress toward flight-representative
software.

## Running it

Requires Python 3.10+. From the repo root:

    python main.py

No external dependencies for the core stack. (HALIA's crew-message
validation uses pydantic; skip HALIA if not installed.)

## Provenance

Concept and architecture by James "Jay" Pratt. Prototype developed with AI
pair-programming assistance (Claude, Anthropic) — documented in commit
history via `Co-Authored-By` trailers. Fault-escalation logic first
demonstrated November 2025; latching and persistent WARNING state added
July 2026.

**2026-07-26** — Jay Pratt + Claude (Anthropic): consolidated the two
parallel event buses onto a single shared `EventBus` (agents were split
across both, so telemetry-derived faults never reached EDEN/HALIA); fixed
GRACIE's WARNING state and added FAULT latching; fixed broken imports that
prevented the app from starting at all; ETHAN now handles `run_diagnostics`;
EDEN now heartbeats its status every telemetry cycle instead of only on
command. Full detail in the commit history.