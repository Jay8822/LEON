# LEON — a step towards the future, for safer space flight

**Not flight software. Not validated. Not ready to fly anything.** That warning isn't a disclaimer buried at the bottom — it's the title of how I want this project read. Everything below is scoped against it.

## What LEON is

LEON is a multi-agent fault-governance architecture for spacecraft — a structured way for independent onboard systems to monitor themselves, flag what's abnormal, escalate what they can't resolve alone, and bring the craft to a safe state without waiting for a human to notice. It's described in full in [`SPEC.md`](SPEC.md), with everything the design assumes but never checks written down separately in [`ASSUMPTIONS.md`](ASSUMPTIONS.md).

## Why it matters

Communication with a spacecraft isn't instant. In Earth orbit the delay is a fraction of a second; at the Moon, about a second each way; by Mars, 4 to 24 minutes each way. For a fault that develops in milliseconds, ground control simply isn't in the loop fast enough to help. The further out missions go, the more a spacecraft has to be able to judge its own faults, escalate sensibly, and only call home when calling home can actually help. LEON is an attempt to work out what that looks like in detail — not just "the computer decides," but a specific, auditable chain of checks, retests, sign-offs and safe states that a reviewer could actually interrogate.

## What's built and tested, honestly scoped

- **`EscalationOrchestrator`** (`agents/escalation_orchestrator.py`, tested in `agents/escalation_orchestrator_test.py`) — the core escalation chain from `SPEC.md`: self-check → orchestrator triage → rerun ladder → clear/unclear consensus → timeout floor; the bypass rule for genuine emergencies; graceful degradation when EDEN goes silent; the four-way sign-off retest ladder, including the "Hold course" reduced-speed state and the post-override rerun with its recurring light flag. Built and tested standalone, against synthetic inputs. **Not yet wired into any real agent.**
- **A simpler Python simulation** (`agents/`, `core/`, `main.py`) — six components (GRACIE, EDEN, ETHAN, LUNAE, HALIA, SystemCoordinator) talking over a shared in-memory event bus. This predates `SPEC.md` and is considerably simpler than what the spec now describes — it's the ground floor, not the destination.
- **A C++ build to NASA/JPL's "Power of 10" rules** (`AI Stack C++ Test Build/`) — a from-scratch redesign, not a port, of the fault-escalation chain for GRACIE, EDEN and the coordinator, written to safety-critical coding constraints. Compiles clean on three toolchains, passes its own test and static-analysis targets.
- **A standalone-process demonstrator** (`distributed/`) — GRACIE and EDEN running as two genuinely separate OS processes over a raw TCP socket, proving the agent code doesn't secretly depend on sharing memory with anything else.

## What it isn't

Not flight software. Not independently reviewed, verified or certified. Not run against any real hardware. The real per-component thresholds, timing windows and retry counts that a real spacecraft would need are explicitly unspecified throughout `SPEC.md` — they need real hardware data I don't have, and I'd rather say "not yet specified" than invent numbers that sound plausible.

## Current status and next steps

Right now the escalation logic exists and is tested in isolation; none of the real agents call into it yet. The plan is to wire them in one at a time, in "ghost mode" first — the orchestrator watching real traffic and logging what it would have decided, without yet being allowed to act, so its judgement can be compared against the current simple wiring before it takes over. After that: testing the detection logic against real, publicly available spacecraft telemetry (starting with ESA's OPS-SAT dataset), then the rest of the agents, then bringing the C++ build up to the same behaviour and proving the two agree.

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
