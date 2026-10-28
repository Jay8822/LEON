# LEON — a step towards the future, for safer space flight

**Not flight software. Not validated. Not ready to fly anything.** That warning isn't a disclaimer buried at the bottom — it's the title of how I want this project read. Everything below is scoped against it.

## What LEON is

LEON is a multi-agent fault-governance architecture for spacecraft — a structured way for independent onboard systems to monitor themselves, flag what's abnormal, escalate what they can't resolve alone, and bring the craft to a safe state without waiting for a human to notice. It's described in full in [`SPEC.md`](SPEC.md), with everything the design assumes but never checks written down separately in [`ASSUMPTIONS.md`](ASSUMPTIONS.md).

## Why it matters

Communication with a spacecraft isn't instant. In Earth orbit the delay is a fraction of a second; at the Moon, about a second each way; by Mars, 4 to 24 minutes each way. For a fault that develops in milliseconds, ground control simply isn't in the loop fast enough to help. The further out missions go, the more a spacecraft has to be able to judge its own faults, escalate sensibly, and only call home when calling home can actually help. LEON is an attempt to work out what that looks like in detail — not just "the computer decides," but a specific, auditable chain of checks, retests, sign-offs and safe states that a reviewer could actually interrogate.

## What's built and tested, honestly scoped

- **GRACIE** (`agents/gracie.py`, `agents/gracie_rulebook.py`) — any-sensor, rule-book-driven health monitoring: an arbitrary set of channels, each judged independently against four senses (level, rate-of-change, sustained drift, and Stillness — a sensor sitting unnaturally still is itself treated as a suspect instrument). Proven to match the batch analysis scripts it was incrementally rewritten from (`agents/gracie_equivalence_test.py`, against real OPS-SAT data and a simulated drift test). Knows about expected causes (a commanded event's predicted size, direction and duration, with tolerance) without ever being told what one is — that judgement stays outside her, in the caller.
- **EDEN** (`agents/eden.py`, tested in `agents/eden_test.py`) — reacts by fault class, not by a blanket "any fault means stop": a non-urgent condition is flagged and logged while the craft keeps running, a major fault commands Hold, and only a boom fault (one that could harm the ship or people) commands Safe mode with its mandatory human sign-off. Replaces an earlier version that sent any fault straight to Safe mode regardless of severity.
- **CHESTER** (`agents/chester.py`) — a ship-wide watcher with no authority of its own: keeps its own record of what every agent announces, tidies what's no longer relevant, and never overrides the agent that actually owns a decision.
- **`EscalationOrchestrator`** (`agents/escalation_orchestrator.py`, tested in `agents/escalation_orchestrator_test.py`) — the core escalation chain from `SPEC.md`: self-check → orchestrator triage → rerun ladder → clear/unclear consensus → timeout floor; the bypass rule for genuine emergencies; graceful degradation when EDEN goes silent; the four-way sign-off retest ladder, including the "Hold course" reduced-speed state and the post-override rerun with its recurring light flag. Exercised today through two narrow, explicitly-labelled stand-in paths — `agents/ghost_mode.py` (watches real traffic and logs what the orchestrator would have decided, without yet acting on it) and `agents/escalation_watch.py` (forwards one specific kind of event into it) — but her own triage/rerun/sign-off machinery is **not yet the live decision path for any agent**.
- **A simulated LEON craft** (`sim/`) — a synthetic, nine-sensor spacecraft built specifically to test detection and reaction where the truth is known in advance: a blueprint and rule book co-designed together, then frozen and committed to git *before* any fault exists, with every correction made during that freeze logged with its reason (`sim/COMMISSIONING.md`). A separate script plants faults the agents never see. Used to prove EDEN's fault-class reaction end to end, run across multiple random seeds, with results reported exactly as they come out — including a real gap it found in the process (a correctly-excused, expected sensor reading on a boom-classed channel can still trip Safe mode) that's flagged for a future fix rather than quietly patched. Full results in `sim/RESULTS.md`.
- **A C++ build to NASA/JPL's "Power of 10" rules** (`AI Stack C++ Test Build/`) — two things, kept distinct: an original, simple two-sensor scaffolding (now marked legacy), and a real **port** of GRACIE's current rule-book core (per-channel rules, all four senses, latching) to the same fixed-memory, bounded-loop constraints. Proven to give identical answers to the Python version — bit-for-bit, down to a 1e-9 tolerance that's reported even when it isn't needed — against a simulated drift test, a real ESA-ADB channel, and *every* OPS-SAT test fragment (529 of them), plus a deliberately engineered test that overflows its own fixed-size buffer on purpose, to prove the overflow is reported rather than silently mishandled. Compiles clean on three toolchains, passes its own test and static-analysis targets. Not wired into any running craft.
- **Real-data testing** (`real_data_tests/`) — GRACIE's detection logic run against real telemetry, not just synthetic fixtures: ESA's OPS-SAT, and ESA's Astrophysics Data Benchmark (ESA-ADB), both labelled with real anomalies. Found real things, not just confirmed the obvious: two channels drifting (not getting noisier) relative to their own thresholds; a real masking effect where a channel already falsely latched can hide a genuine fault underneath it; counting false alarms per-episode instead of per-sample changes the picture by roughly 5x on the channels worst affected. Several further real datasets (a NASA testbed with injected faults, ESA's Mars Express power telemetry, NASA battery-ageing data, an aircraft-engine degradation dataset) are downloaded and profiled as future candidates, not yet tested against.
- **A standalone-process demonstrator** (`distributed/`) — GRACIE and EDEN running as two genuinely separate OS processes over a raw TCP socket, proving the agent code doesn't secretly depend on sharing memory with anything else.

## What it isn't

Not flight software. Not independently reviewed, verified or certified. Not run against any real hardware. The real per-component thresholds, timing windows and retry counts that a real spacecraft would need are explicitly unspecified throughout `SPEC.md` — they need real hardware data I don't have, and I'd rather say "not yet specified" than invent numbers that sound plausible.

## Current status and next steps

Ghost mode is running and real-data testing is underway, both further along than "the plan" below used to describe — this section is about what's actually left. Known gaps, in rough order:

- EDEN can't yet tell a correctly-excused, expected reading apart from a genuinely concerning one on the same channel — found by testing against the simulated craft, not yet fixed.
- LUNAE still has its own older "any fault means hold" reaction, independent of EDEN's newer, more specific judgement — a leftover from before EDEN had fault classes at all.
- The simulated craft's dying-battery fault still uses an invented decline curve; real NASA battery-ageing data is downloaded and ready to swap in.
- CHESTER doesn't yet escalate a condition that's been noticed but never formally flagged for a long time, even though that's exactly the kind of thing a ship-wide watcher should catch.
- `EscalationOrchestrator`'s own triage/rerun/sign-off chain is proven in isolation but still isn't any agent's actual, live decision path — only watched and compared against from the side.
- The C++ port covers GRACIE's settled core; it doesn't yet cover the newest changes (sized expected causes, Stillness, per-sense fault classes) — deliberately held back until the Python side itself has settled further.
- Real-data testing so far covers 16 selected channels out of over 100 monitored across both ESA-ADB missions; broadening that, and actually testing against the newly profiled datasets (not just downloading and reading their documentation), are both queued.

## How it was built

With AI pair-programming assistance throughout — Claude (Anthropic), credited openly in every commit via `Co-Authored-By` trailers, and in per-file "Updated" headers for exactly what changed when. The architecture, the decisions, and every judgement call are mine; Claude helped write, test, and challenge the implementation of them.

## About me

I'm Jay Pratt, founder of Leon Systems Ltd. I'm self-taught, and come from outside the space industry. LEON started with a simple question: could the way an electric car splits control between independent units work on a spacecraft?

## Looking for a partner

I'm looking for a partner to help take this further — building it out and, just as importantly, testing it properly. If you work in spacecraft fault management, safety-critical software, or formal verification and this looks interesting, I'd like to hear from you.

## Where this could go

My hope is for this to grow from a personal project into a proper system, and eventually into a licensable product line that could help fund further research into exactly the kind of fault-governance work this project is trying to get right. That's a goal, not something already underway — everything above describes where the project actually is today.

## Contact

leonsystemsltd@gmail.com
