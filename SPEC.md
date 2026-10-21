# LEON — Agent Behaviour Specification

Source of truth for the LEON agents. Written by James (Jay) Pratt in his own words, with AI assistance (Claude) translating intent into spec language. Where this spec differs from the current code, the code is the thing that needs changing, not the spec. Gaps are marked **Status: not built**.

Version: draft, October 2026.

---

## Core principle

Anything that isn't normal is flagged. Anything that rises without reason is flagged. Everything is logged, regardless.

---

## Agents

| Agent | Role |
|---|---|
| GRACIE | Health monitor, ship-wide |
| EDEN | Final judge — escalation point of last resort within the agent tier |
| ETHAN | Propulsion and engine management |
| LUNAE | Navigation — points the way to go |
| HALIA | Crew and ground control interface. The only agent with an LLM, and no authority to act |
| SystemCoordinator | HALIA's bridge and containment gatekeeper; periodic diagnostics |
| Orchestrator | Separate seventh component. Traffic controller and quality control ahead of EDEN |

Each agent is self-sufficient in its own domain and can act without permission. Anything it cannot resolve alone goes up the chain.

---

## GRACIE — health monitor

- Any monitored parameter crossing its safe threshold is flagged **independently**. Temperature does not need radiation to also be high, and vice versa.
- Three severities: **flagged**, **logged for investigation** (a spike that returns to normal), and **nominal**.
- A rise is judged against context from other agents on the bus, not in isolation. Expected causes (engine burn from ETHAN, radiation cloud, manoeuvre) are logged. No explanation on the bus means flagged as an early warning.
- Crossing a safe parameter by more than a set margin is flagged regardless of context.
- Status: **not built** (current code requires temp AND radiation together; that was synthetic-test scaffolding). Context-aware flagging, the logged-for-investigation severity and the independent per-parameter check are all work packages.

---

## ETHAN — propulsion

- Scope: thrust, fuel consumption and injection, temperature, radiation, exhaust, gases released or produced.
- Talks to LUNAE for navigational instructions, and to GRACIE for heat and radiation cross-reference.
- Has his **own** radiation reading specific to the engine. Also listens to GRACIE's readings to check whether a ship-wide rise could have come from his engine.
- Correlation logic (the deliberate inverse of GRACIE's "expected = logged" rule):
  - Rise is a **direct, confirmed result of the engine**: **raised**. Treated as more serious, because it is a confirmed real problem.
  - Correlates but is **not** a direct engine result: **noted by both agents concerned and logged**, not raised.
- Failure modes split into two timing tiers (see Timing below).
- Status: **not built**. Current code only responds to commands.

---

## LUNAE — navigation

- Sits at the front of the ship and points the way. Tracks position, heading, star-tracker data and orbital elements.
- Instructs ETHAN for propulsion and telemetry.
- Fault conditions: veering off course, running at an angle, any deviation from the directed course, losing track of the destination, or a major course correction being required.
- **Self-correction first**: she instructs ETHAN to correct course using whatever is onboard (thrusters, main engine thrust) before escalating.
- Also scans **every** other agent's raised faults, to check whether a fault elsewhere originated from her instruction (engine bay, comms, anywhere).
- **HOLD** is a last resort, only after self-correction has failed and human interaction is taking longer than a set time. HOLD means the ship comes to a complete stop and holds its **current position** (not its course) until released.
- Status: **not built**. Current code drops straight to HOLD on any fault, which contradicts this spec.

---

## HALIA — crew and ground control interface

- Primary use: manned missions, adapted for unmanned. The crew's and ground control's eyes and ears of the ship. Can pull data from any agent on request.
- The LLM sits here and only here. Assists crews with logging and research (for example ISS-type sampling work). On unmanned missions, the deeper assistant interface runs only when specifically requested (for example, voice notes from a satellite operator).
- **Hard constraint**: she cannot directly fix or change anything. She can prompt the correct agent to look at an issue, and relay a message back to crew or ground control. Nothing more.
- When HALIA raises something, the agent checks it. If the agent and a human both say it's fine, it is logged and closed, **but a review stub is left** to find out why HALIA raised it, in case her boundaries have a hole.
- **LLM containment rule**: no LLM component may touch any other agent except via specifically instructed data, and that bridge is **single-use, one direction at a time**. Each crossing is an individually authorised one-shot channel. No standing connection.
- LLM active on manned missions only. May be offered to ground control when a threshold number of agents are in use.
- Status: **not built**. Current code relays crew commands and reports status only.

---

## SystemCoordinator — HALIA's bridge and containment gatekeeper

- HALIA never reaches into an agent directly. Everything goes through the coordinator.
- For every request it: checks the request is authorised, lets exactly one crossing through, then closes. This is what makes the single-use bridge actually single-use. It is a safety-critical component.
- Runs consistent diagnostics every few minutes. Surfaced to crew as a small green light flash and a soft chirp, quiet enough not to wake anyone. Runs in the background for ground control on unmanned missions.
- Status: **not built**. Current code has an open `send_command()` with no authorisation check.

---

## Orchestrator — separate seventh agent (not part of EDEN)

- A controller in the middle of the ship. Directs all incoming and outgoing data flow, not just traffic to EDEN.
- Priority messages are pushed to the front of the queue.
- **Sees all and knows all.** It has to, otherwise it could send the wrong thing to the wrong place.
- Real job: quality control **before** EDEN sees anything. Holds EDEN's rules as its priority signals, plus its own harder parameters.
- Status: **not built**. `agents/orchestrator.py` is a scripted two-step diagnostic runner and is **not** this component.

### Orchestrator bypass

- Two cases bypass the gate: ETHAN's "I need a human now" escalation, and **any critical malfunction** from any agent.
- A bypass goes straight to where it needs to go, and **leaves a note** to the orchestrator that it happened. The orchestrator never loses awareness; it only does not get to gate the fast path.

---

## EDEN — final judge

- Not a general dispatcher. She is the escalation point of last resort within the agent tier. She only receives what falls outside an agent's own parameters. Her volume is naturally low.
- Validates each report against the reporting agent's rules **and** her own parameters. Both must align before she treats it as real.
- Holds a copy of every agent's rule set, plus her own harder rule set, including the plus/minus tolerance around each agent's parameters. This lets her judge priority, and stops any agent acting outside protocol.
- Confirms that anything raised has been fixed, even when an agent fixed it itself. Keeps one authoritative log.
- Status: **not built**. Current code acts directly on GRACIE's FAULT report with no validation.

---

## Escalation chain (in order)

1. **Self-check.** Each agent checks the incoming information against its own parameters, and where relevant against adjoining agents' parameters. It fixes what it can without escalating.
2. **Load varies by mission phase.** Heavy traffic at take-off and similar phases; quieter at cruise. Expected behaviour, not a bug.
3. **Unresolved items go to the orchestrator first**, not EDEN.
4. **Orchestrator checks.** Against the rules every agent has, and its own harder parameters.
   - Violated outright: straight to EDEN.
   - Conflicting but not clearly a fault: check against the sending agent's rules and its own, then decide.
5. **Orchestrator decides**: send to EDEN, or send an instruction back to the agent (for example, "rerun the test").
6. **Rerun logic.** The agent reruns the test, double-checking everything each time.
   - Same result twice: raised to EDEN.
   - Different result: runs again. That rerun becomes the agent's third check, sent back to the orchestrator.
   - Results keep differing across checks: sent to EDEN regardless of parameters. Instability is itself grounds for escalation.
7. **Clear path.** When every agent involved sends an all-clear, the orchestrator releases the latch and all agents log a clear.
8. **Unclear path.** If even one agent sends an unclear result, raised for human interaction. Consensus is required to stand down; any dissent goes to a person.
9. **Timeout floor (true last resort).** If data from any part conflicts with all parameters and persists beyond a set number of processes, or a set time, raised for human interaction. No infinite retry loops.

Philosophy behind the limits: escalating to a human is a cost-benefit decision. "Flagged for human interaction is asking for help on a budget." Where conflict is more saturated, it is raised sooner rather than exhausting every internal retry.

Status: **not built**.

---

## Fault lifecycle and release

### Standard release (agent-resolved faults)

Agent latches its flag, reports to EDEN, EDEN acts and confirms, then the originating agent releases its own latch and logs. The latch is released by the agent that raised it, not by an external command or by EDEN reaching in.

### Four-way sign-off (human-interaction faults only)

Release requires all four to confirm and log:

1. Human confirms the fix
2. Orchestrator confirms
3. Originating agent confirms
4. EDEN confirms

Reason: humans can miss things (a door left open, a flap not closed, a switch missed). The machine-side sign-off catches what a person might overlook.

### Traceability

EDEN's main log is the master index. Every entry traces back to its originating agent with a timestamp. Nothing is anonymous.

---

## Graceful degradation when EDEN does not respond

The orchestrator is the doorman. It is the only component that talks to EDEN directly. If it knocks and EDEN does not answer, EDEN is either deep in a problem or faulty.

The sequence starts at the agent that raised the flag. The response depends on the fault.

### Fault classes

- **Major fault**: an issue the agent cannot fix itself, because it takes too long, is too complicated, or needs human approval. Examples: a major course correction, an engine fault, a risk to the system.
- **Non-urgent fault**: anything else.

If the fault class is unknown, treat it as major.

### Detecting EDEN's silence

The orchestrator applies a timeout, starting the moment it sends to EDEN (the knock). One clock per fault — its length depends on fault class, with major faults using a shorter window than non-urgent faults. If EDEN has not answered within that window, EDEN is treated as unresponsive. Both window lengths are configurable parameters, to be set from hardware data. No default values.

### Outcomes

| Situation | Action |
|---|---|
| Major fault, EDEN unresponsive | Craft holds. Passed to a human |
| Non-urgent fault, EDEN unresponsive, fault still live | Flagged for human review. Not passed directly. Craft keeps running |

"Flagged" means queued for a person to review. "Passed" means a person is actively alerted.

Status: **not built**.

---

## Timing

Deadlines come from how fast the **failure mode** unfolds, not from how fast the computing can run. Real values must be set against real hardware characteristics.

- **Fast-acting faults** (pressure rises or drops, uncontrolled thrust, burn-out): millisecond response.
- **Slow-developing faults** (thermal drift, degradation): sub-second to seconds, with time to settle and to take corrected readings. Reacting too fast to a slow fault produces false positives from transients that would have settled.
- Drift detection cannot be millisecond-fast. Noticing a trend physically requires elapsed time.
- HALIA's LLM inference is hundreds of milliseconds to seconds. Another reason she is kept away from anything time-critical.

---

## Hover — standby state

- Works like a TV on standby. A system drops to low power until an instruction or a scheduled activation.
- The responsible agent still monitors its domain in hover, at reduced level (basics and important parts only).
- EDEN and SystemCoordinator never hover. GRACIE can flip in and out but is mainly on. ETHAN can shut down fully and wakes on prompt. LUNAE always keeps at least one eye open. Some agents only power down when the whole ship does.
- Power not in use goes back into the main batteries.
- Cooling systems always stay on. Fuel systems follow ETHAN's state.
- Status: **not built**.

---

## Cross-referencing principle

Never judge in isolation. Each agent checks its own domain against the wider picture. GRACIE correlates a rise against what the ship is doing. ETHAN correlates his engine reading against GRACIE's. LUNAE correlates other agents' faults against her own instructions.

---

## Known exceptions

- **ETHAN** skips the normal orchestrator retry ladder for "I need a human now" and critical malfunctions. Deliberate, and documented as an exception. The bypass is logged to the orchestrator (see above).

---

## Open items (not yet specified)

- Real numbers for every threshold currently written as "safe threshold", "margin", "X amount" or "a set time". Need hardware data.
- Assumptions list: what the system takes for granted without checking. In progress; GRACIE done (sensors honest, stuck sensor, messages arrive, clocks agree, context from other agents accurate, EDEN's confirmation real, logging never fails).
- Formal specification and verification approach. Partner work.
- Assurance case approach. Partner work.

---

## Build gap summary

Every component above is marked **not built** or partly built. The current code is a skeleton of the philosophy. This spec describes the intended system.
