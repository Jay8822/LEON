# LEON — Agent Behaviour Specification

Source of truth for the LEON agents. Written by James (Jay) Pratt in his own words, with AI assistance (Claude) translating intent into spec language. Where this spec differs from the current code, the code is the thing that needs changing, not the spec. Gaps are marked **Status: not built**.

Companion document: `ASSUMPTIONS.md` lists what the design assumes but never checks.

Version: draft, October 2026.

---

## Core principle

Anything that isn't normal is flagged. Anything that rises without reason is flagged. Everything is logged, regardless.

---

## General principles

- Everything and everybody is treated the same. Agents and humans get the same rules, checks and logging. Bypasses change speed, never rules: they are still logged, still leave a note, and still need signing off.
- Each agent's rule book defines "normal". The rule book is that agent's laws; anything outside it is abnormal by definition.
- The rule book changes for each craft and mission type.
- Every number carries its units, so a units mix-up is caught automatically.
- Every received message is checked against the message sent, as well as the usual rule-book check and retest.
- Speed matching: any agent that sends instructions must be able to respond as fast as the agent receiving them.
- Questioning instructions: if an instruction follows the rules but looks wrong, the receiver questions it. The sender rechecks and resends. If it comes back the same, it is carried out, monitored for a set time to check it caused no faults, then checked again a while later. A clash between an instruction and the readings is itself a fault. This applies to human instructions too.
- System-wide heartbeat: any component that goes silent is pinged continuously by the others until it answers, and vice versa.
- Power priority: the always-on components (EDEN, orchestrator, SystemCoordinator) get first claim on power, in any crisis, not just hover.

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
| CHESTER | Eighth component. Ship-wide watcher with no authority: keeps timers and long memory, tells the relevant agent |

Each agent is self-sufficient in its own domain and can act without permission. Anything it cannot resolve alone goes up the chain.

---

## GRACIE — health monitor

- Any monitored parameter crossing its safe threshold is flagged **independently**. Temperature does not need radiation to also be high, and vice versa.
- Rate-of-change: GRACIE also watches how fast a reading moves, not just its level — see "Rate-of-change sense (stack-wide)".
- Leash: GRACIE also watches for slow, sustained drift, not just level and jump — see "Leash — drift sense (stack-wide)".
- Ageing: her rule book is recalibrated over a long mission as components age and "normal" shifts — see Ageing.
- Three severities: **flagged**, **logged for investigation** (a spike that returns to normal), and **nominal**.
- Logged-for-investigation items are announced on the bus, with the current readings, for CHESTER to watch over — every jump, and every time a channel enters or leaves a logged/flagged state, once per transition, never repeated for a condition that's still ongoing — see "Leash — drift sense (stack-wide)" and CHESTER.
- A rise is judged against context from other agents on the bus, not in isolation. Expected causes (engine burn from ETHAN, radiation cloud, manoeuvre) are logged. No explanation on the bus means flagged as an early warning.
- Crossing a safe parameter by more than a set margin is flagged regardless of context.
- New crossing while already latched: if a channel is already latched
  (FAULT, or a hard leash) and a new, separate crossing or event
  happens on it, that is logged as a fresh event in its own right,
  never silently swallowed by the existing latch. CHESTER keeps watch
  on any latch left on for a long time, so a persistent latch doesn't
  quietly absorb everything that happens underneath it. See
  `ASSUMPTIONS.md` A76.
- Deep health sweep: a stream of small faults is itself abnormal. GRACIE then runs a full health test down to every part she manages, so, for example, a blown fuse is found. Ship-wide — every agent runs its own sweep under the same trigger (see Cross-referencing principle).
- Status: **built** — any-sensor, rule-book-driven, independent per-channel level/jump/leash (`agents/gracie.py`, `agents/gracie_rulebook.py`). Proven to give the same answers as the batch scripts it was rewritten from (`agents/gracie_equivalence_test.py`, against both real OPSSAT-AD data and the simulated leash test). Wired into the real `main.py` demo; confirmed still compatible with ghost mode. Also built, 26 October 2026: logging a fresh event on a new crossing while already latched, and an `expected_causes` input that logs a level crossing instead of flagging it (both `agents/gracie.py` module docstring, point 12) — GRACIE still has no idea what counts as an expected cause or where one comes from; deciding that stays entirely outside her, in real_data_tests/ for now. **Not built**: context-aware flagging for anything beyond an already-decided expected cause (judging a rise against what other agents report more generally), jump's cross-check, leash's context-gating (all three need other agents' signals GRACIE doesn't have yet), and the deep health sweep. Ageing is covered separately — see Ageing. CHESTER (built, `agents/chester.py`) already watches and light-flags what GRACIE announces today.

---

## ETHAN — propulsion

- Scope: thrust, fuel consumption and injection, temperature, radiation, exhaust, gases released or produced.
- Talks to LUNAE for navigational instructions, and to GRACIE for heat and radiation cross-reference.
- Has his **own** radiation reading specific to the engine. Also listens to GRACIE's readings to check whether a ship-wide rise could have come from his engine.
- Correlation logic (the deliberate inverse of GRACIE's "expected = logged" rule):
  - Rise is a **direct, confirmed result of the engine**: **raised**. Treated as more serious, because it is a confirmed real problem.
  - Correlates but is **not** a direct engine result: **noted by both agents concerned and logged**, not raised.
- Leash: a sustained drift is watched for too, with the same inverse correlation logic — a confirmed engine-caused drift stays tight even when GRACIE's matching leash loosens. See "Leash — drift sense (stack-wide)".
- Timing: fast faults (pressure, uncontrolled thrust, burn-out) get millisecond responses. Slow faults (thermal drift, degradation) get seconds, with settling time (see Timing below). Any possible boom fault, including a false pressure reading, means safe mode: a false shutdown is accepted over a real boom.
- Status: **not built**. Current code only responds to commands.

---

## LUNAE — navigation

- Sits at the front of the ship and points the way. Tracks position, heading, star-tracker data and orbital elements.
- Instructs ETHAN for propulsion and telemetry.
- Fault conditions: veering off course, running at an angle, any deviation from the directed course, losing track of the destination, or a major course correction being required.
- **Self-correction first**: she instructs ETHAN to correct course using whatever is onboard (thrusters, main engine thrust) before escalating.
- Also scans **every** other agent's raised faults, to check whether a fault elsewhere originated from her instruction (engine bay, comms, anywhere).
- **HOLD** is a last resort, only after self-correction has failed and human interaction is taking longer than a set time. HOLD means the ship comes to a complete stop and holds its **current position** (not its course) until released. See "Ship safe states" for the full taxonomy of Hold / Hold course / Safe mode.
- Position scan, three cases: (1) wrong star suspected: scan for what matches the original instructions, and correct if it doesn't match. (2) Everything matches: carry on. (3) Right star and heading, but slightly off course, for example from gravity: slow drift, quietly monitored and checked regularly. A wrong star corrected with no human involved gets a three-way sign-off plus a log entry. Note: the position check must use a source independent of the possibly-wrong star, such as a second star, or position worked out from speed and time.
- Status: **not built**. Current code drops straight to HOLD on any fault, which contradicts this spec.

---

## HALIA — crew and ground control interface

- Primary use: manned missions, adapted for unmanned. The crew's and ground control's eyes and ears of the ship. Can pull data from any agent on request.
- The LLM sits here and only here. Assists crews with logging and research (for example ISS-type sampling work). On unmanned missions, the deeper assistant interface runs only when specifically requested (for example, voice notes from a satellite operator).
- **Hard constraint**: she cannot directly fix or change anything. She can prompt the correct agent to look at an issue, and relay a message back to crew or ground control. Nothing more.
- When HALIA raises something, the agent checks it. If the agent and a human both say it's fine, it is logged and closed, **but a review stub is left** to find out why HALIA raised it, in case her boundaries have a hole.
- **LLM containment rule**: no LLM component may touch any other agent except via specifically instructed data, and that bridge is **single-use, one direction at a time**. Each crossing is an individually authorised one-shot channel. No standing connection.
- LLM active on manned missions only. May be offered to ground control when a threshold number of agents are in use.
- Anything shown on a screen comes directly from the agent, never from HALIA; HALIA only speaks the result. Her system is completely separate apart from the single bridge. She cannot read EDEN's logs even if asked, and keeps her own logs, time-synced with the others. Identity checks: video both ways, plus voice recognition, fingerprint, passcode and retina where available.
- Status: **not built**. Current code relays crew commands and reports status only.

---

## SystemCoordinator — HALIA's bridge and containment gatekeeper

- HALIA never reaches into an agent directly. Everything goes through the coordinator.
- For every request it: checks the request is authorised, lets exactly one crossing through, then closes. This is what makes the single-use bridge actually single-use. It is a safety-critical component.
- A crossing needs both the crew's request and the rules to agree; the crew's rules and HALIA's must match. If the coordinator fails, the door fails shut, and only a crew or ground control sign-off reopens it. A stuck crossing is forced closed when its time runs out, then flagged, logged and investigated.
- Runs consistent diagnostics every few minutes. Surfaced to crew as a small green light flash and a soft chirp, quiet enough not to wake anyone. Runs in the background for ground control on unmanned missions.
- Status: **not built**. Current code has an open `send_command()` with no authorisation check.

---

## Bus

- Agents switch to the bypass, which is a separate physical path wired to the logs, if the bus fails — and the ship goes to safe mode.
- Status: **not built**. No separate physical bypass path exists in code.

---

## Orchestrator — separate seventh agent (not part of EDEN)

- A controller in the middle of the ship. Directs all incoming and outgoing data flow, not just traffic to EDEN.
- Priority messages are pushed to the front of the queue.
- **Sees all and knows all.** It has to, otherwise it could send the wrong thing to the wrong place.
- Real job: quality control **before** EDEN sees anything. Holds EDEN's rules as its priority signals, plus its own harder parameters.
- Orchestrator failure: the ship goes to safe mode and a human is needed. EDEN covers meanwhile, working from logs and test results in priority order, and pings the orchestrator until it answers. EDEN receives all traffic in this case; acceptable, because traffic drops in safe mode.
- Status: **built, not wired into agents** — the escalation logic lives in `EscalationOrchestrator` (`agents/escalation_orchestrator.py`). `agents/orchestrator.py` is a scripted two-step diagnostic runner and is **not** this component.

### Orchestrator bypass

- Two cases bypass the gate: ETHAN's "I need a human now" escalation, and **any critical malfunction** from any agent.
- A bypass goes straight to where it needs to go, and **leaves a note** to the orchestrator that it happened. The orchestrator never loses awareness; it only does not get to gate the fast path.

---

## CHESTER — ship-wide watcher, no authority

- A watcher with no authority, like HALIA. It watches, remembers, keeps timers, and tells the relevant agent. The owning agent makes every decision. A PA for the agents, not a manager.
- Agents announce their own faults and anomalies on the bus; CHESTER keeps watch over them. Built and watching GRACIE's announcements today; other agents don't announce anything yet.
- He logs as he goes: every reading he reads and every timer he sets, for traceability.
- Its job is the slow, long-memory work, to take strain off the other agents:
  - Leash timers — how long a pull has been going, and when it reaches the hard duration.
  - Long-held latches — flags a latch (FAULT or hard leash) that's
    stayed on an unusually long time, so a persistent fault doesn't
    quietly swallow whatever happens next underneath it.
  - Items logged for investigation, so they aren't forgotten.
  - Repeating coincidences between unrelated jumps ("spike on X, jump on Y, again").
  - Light-flag reminders on every timed self-check cycle.
- Ghost memory: a temporary working memory that refreshes every 10 minutes under optimal conditions (rule-book setting; 10 minutes is the intended starting value). Old layers are never fully deleted: they fade into a ghost memory he can still access after a restart, overload or power disruption, so he can pick up where he left off.
- Storage-full rule: storage is finite. The oldest ghost layers may be cleared to make room only once they are safely in his permanent log. He flags for a human when nearing full. Nothing is ever dropped silently.
- End of each mission or day: he tidies his ghost memory, removing data the rule book defines as irrelevant, and commits it to the permanent record. The raw log is never edited or deleted; only the ghost memory (his working summary) is trimmed.
- Owns long-term ageing tracking and each sensor's historical baseline — memory over time, same as everything else here. See Ageing.
- Does not do the fast checks. Level and jump stay with each agent, because they can't wait for a middleman (e.g. ETHAN's millisecond responses).
- If an agent ignores him: he notifies the orchestrator, which pings that agent to confirm it's active, and a flag is added to CHESTER's log.
- How it differs from the orchestrator: the orchestrator handles traffic, priority and escalation in the moment; CHESTER handles memory over time.
- If CHESTER goes down: the system-wide heartbeat pings it until it comes back; if it doesn't, it's flagged for human interaction. Agents carry on with their own fast checks meanwhile. No safe mode, because CHESTER never makes decisions.
- Status: **built** (`agents/chester.py`) — watches "chester/watch" generically (tested against GRACIE's real announcements, not just synthetic ones); ghost memory (layers, refresh, storage-full rule, end-of-mission tidy, raw log untouched); light-flag reminders for open items; the ignored-agent check through `EscalationOrchestrator.ping_agent()` (now built too, not a stub); answers a heartbeat ping if one arrives. Wired into `main.py` alongside GRACIE and ghost mode. **Not built**: the system-wide heartbeat mechanism itself (nothing pings anyone yet, for any component); CHESTER receiving anything beyond what GRACIE currently announces (jump, entering/leaving a logged or flagged state, a settled leash pull) — other agents don't announce anything yet; whether leash timing itself ever moves from GRACIE into CHESTER, rather than CHESTER just keeping his own parallel record of it, is undecided.

---

## EDEN — final judge

- Not a general dispatcher. She is the escalation point of last resort within the agent tier. She only receives what falls outside an agent's own parameters. Her volume is naturally low.
- Validates each report against the reporting agent's rules **and** her own parameters. Both must align before she treats it as real.
- Holds a copy of every agent's rule set, plus her own harder rule set, including the plus/minus tolerance around each agent's parameters. This lets her judge priority, and stops any agent acting outside protocol.
- Confirms that anything raised has been fixed, even when an agent fixed it itself. Keeps one authoritative log.
- Challenging EDEN: an agent that sees EDEN's ruling doesn't match the rules challenges it. The challenge is passed to a human, and a retest runs automatically, so both results are ready when the human picks it up. If no human can be reached, the orchestrator stands in for EDEN: it checks against its own rules and asks the agent to retest. Logged, flagged and investigated.
- Loop detection: if the same agent triggers safe mode a second time, that agent becomes the suspect. If the rules check out and sign-off is complete, the agent is inspected against its own rules and checked for cross-wiring.
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

Status: **built, not wired into agents** (`EscalationOrchestrator`, `agents/escalation_orchestrator.py`).

---

## Ship safe states

From mildest to most serious:

| State | What happens |
|---|---|
| Hold course | Keep the current heading, at reduced speed |
| Hold | Stop and stay at the current position |
| Safe mode | Everything stops and tests itself, priority tests first. Low power. Stay as close to the original position as possible without wasting fuel, so comms in a blackout zone don't take longer than needed |

"The craft holds", wherever it appears in this spec, means Hold.

Two kinds of Hold, with different release conditions:
- **Planned hold**: set by a crew or ground control instruction. Ends when that instruction says.
- **Fault hold**: triggered by a fault. Ends only when it is signed off, per the Sign-off rules below.

---

## Sign-off rules

| Situation | Sign-off |
|---|---|
| Agent fixed it itself | Agent + EDEN |
| A human interacted with the fault at any point | Four-way: human, orchestrator, agent, EDEN |
| Human can't be reached within the delay window, and it isn't a boom fault | Three-way: orchestrator, agent, EDEN |
| Boom fault (anything that could harm the ship or people) | Safe mode. Must wait for a human. Always four-way |
| Fault fixable with other agents' help | Fixed, flagged, logged |
| Any party needed for a sign-off is unavailable | Safe mode. Something is wrong that could get worse if ignored |

The human delay window (row 3) is a separate configurable parameter, no default — it depends on the mission's comms delay.

"Unavailable" (last row) is defined by the heartbeat (see General principles): a party that doesn't answer pings within its own heartbeat window is unavailable. A party that answers but hasn't signed off yet is simply "not confirmed" — the normal retest ladder, not this row. The heartbeat window is also a separate configurable parameter, no default.

Not a clash: a non-urgent fault with EDEN silent is flagged while the craft keeps running. Nothing is being released, so no sign-off is needed and safe mode does not trigger.

---

## Fault lifecycle and release

See "Ship safe states" and "Sign-off rules" above for the taxonomy these mechanisms use.

### Standard release (agent-resolved faults)

Agent latches its flag, reports to EDEN, EDEN acts and confirms, then the originating agent releases its own latch and logs. The latch is released by the agent that raised it, not by an external command or by EDEN reaching in.

### Four-way sign-off (human-interaction faults only)

Release requires all four to confirm and log, in any order:

1. Human confirms the fix
2. Orchestrator confirms
3. Originating agent confirms
4. EDEN confirms

Reason: humans can miss things (a door left open, a flap not closed, a switch missed). The machine-side sign-off catches what a person might overlook.

### Sign-off retest and escalation

If one party has not confirmed once the other three have, all four retest.

- **Boom fault** (the most serious kind of major fault — anything that could harm the ship or people): no retest ladder, no give-up. Safe mode, and it always waits for a human — see Sign-off rules above.
- **Other major faults**, still not confirmed after the retest: craft stays held, flagged for further investigation. No override path.
- **Non-urgent fault**: a manual override becomes available for a human to use, but only after a *double* retest (retest twice, not once). The override is optional — if nobody uses it and the double retest still fails, the craft automatically treats the fault as major, except it holds course at reduced speed instead of coming to a full stop (see "Hold course" below).
- In every other case (confirmations still pending, no gap yet to react to), the hold stays as it was.

### Hold course — reduced-speed state

A state distinct from LUNAE's HOLD (complete stop, holds current position — see LUNAE section). Hold course means the craft continues on its current heading at reduced speed rather than stopping outright. Used only as the non-urgent-fault fallback above.

### After a manual override

Once a human uses the override, the originating agent reruns its test, to check the fault isn't spreading to other parts or creeping.

- **Fault gone**: logged as cleared.
- **Fault still present**: logged for a person to pick up, and a light flag is raised on every timed self-check cycle until someone deals with it. The cycle interval is a configurable parameter (expected range 5–60 minutes). No default value.

"Light flag" means the same as "flagged" (queued for review), repeated each cycle. It does not actively alert anyone.

### Traceability

EDEN's main log is the master index. Every entry traces back to its originating agent with a timestamp. Nothing is anonymous.

Status: **built, not wired into agents**. The four-way sign-off retest ladder, "Hold course" state, and post-override rerun are implemented in `EscalationOrchestrator` (`start_signoff()`, `confirm()`, `use_override()`, `override_unused()`, `check_after_override()`, `light_flag_tick()` — `agents/escalation_orchestrator.py`), tested in `agents/escalation_orchestrator_test.py`. The boom-fault exception above is newly specified, not yet built — this was a documents-only pass. "Standard release" and "Traceability" above are not part of this build either.

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

Status: **built, not wired into agents**. `EscalationOrchestrator.send_to_eden()` / `check_eden_silence()` in `agents/escalation_orchestrator.py`, tested in `agents/escalation_orchestrator_test.py`.

---

## Timing

Deadlines come from how fast the **failure mode** unfolds, not from how fast the computing can run. Real values must be set against real hardware characteristics.

- **Fast-acting faults** (pressure rises or drops, uncontrolled thrust, burn-out): millisecond response.
- **Slow-developing faults** (thermal drift, degradation): sub-second to seconds, with time to settle and to take corrected readings. Reacting too fast to a slow fault produces false positives from transients that would have settled.
- Drift detection cannot be millisecond-fast. Noticing a trend physically requires elapsed time.
- HALIA's LLM inference is hundreds of milliseconds to seconds. Another reason she is kept away from anything time-critical.

---

## Hover — standby state

Hover works like a TV on standby. It diverts power away from parts of a system that are not in use. Spare power goes back to the main batteries.

Entering hover:
- An agent decides for itself to enter hover.
- EDEN must sign off first.
- A note goes to the orchestrator, so every component knows that agent is in hover.
- An agent with a live fault may not enter hover. It follows normal fault procedure until the fault is fixed or a manual override is used.

Monitoring in hover:
- Parts with no power have nothing to monitor.
- Anything still powered is monitored as normal.

Per-component rules:
- EDEN, the orchestrator and the SystemCoordinator never hover.
- LUNAE: navigation always stays online.
- GRACIE: may hover, but mostly stays on.
- ETHAN: may shut the engines down, but never shuts himself down. He stays ready for thrust instructions, and is woken by an instruction from GRACIE, LUNAE or EDEN.
- HALIA: may hover, but always listens for the crew or ground control, who wake her.
- Cooling systems always stay on. Fuel systems follow the engine state.

Status: **not built**.

---

## Rate-of-change sense (stack-wide)

- Every agent watches not only the level of a reading ("how high is it?") but also how fast it changes ("how fast did it move?"). A reading can jump abnormally while staying inside its normal range.
- A jump bigger than that channel's normal step size is logged for investigation immediately (the existing severity: "a spike that returns to normal is logged for investigation").
- Any agent that detects a jump reports it on the bus, so other agents can cross-reference it.
- Cross-check: when a jump is detected, check whether a related agent or channel reported a jump or an event in the same time window. The rule book says which channels and agents are linked; no assumptions about relationships beyond the rule book.
  - Corroborated (a related jump or event in the window): flagged.
  - Uncorroborated (nothing related moved): stays logged for investigation only.
  An unrelated jump in the same window is never discarded, even though it doesn't corroborate: it's logged against the original jump with a note recording both — what jumped, where, and at what time (for example, "spike on X at time T; unrelated jump on Y at the same time T"). Coincidences don't cause a flag, but repeated unrelated coincidences can be spotted on review, and may reveal a link the rule book doesn't know about yet.
  This keeps lone jumps quiet, which also guards against alert overload (see `ASSUMPTIONS.md` A64).
- The time window looks both before and after the jump, centred on it. Because it looks forward, the flag-or-log decision isn't final until the window has passed. Acceptable, because the decision is only ever between a quiet log and a flag — never a safety action.
- The normal step size for each channel comes from its rule book, measured as a rate (change per second), consistent with "every number carries its units". The time window for cross-checking is a separate setting. Neither has a default value.
- A third sense, for drift too slow to be a jump but too sustained to be normal wobble, is the leash — see "Leash — drift sense (stack-wide)".
- Status: GRACIE — built, on her own channels (`agents/gracie.py`). The cross-check (a related agent/channel corroborating in the same window) is **not built** — it needs other agents' signals GRACIE doesn't have yet. Everyone else — **not built**.

---

## Leash — drift sense (stack-wide)

- Every agent with readings now has three senses, each on a different timescale:

| Sense | Asks | Catches |
|---|---|---|
| Level | How high is it? | Readings outside normal |
| Jump | How fast did it move, just now? | Sudden spikes |
| Leash | Where has it been heading, over a while? | Slow drift |

- The leash ties each reading to its normal behaviour. Normal wobble is allowed: that's the slack (a dead-band, or short-term averaging), so the leash doesn't twitch constantly.
- When a reading's average slope over a sliding window crosses the channel's single slope limit and keeps going, the leash begins.
- Two strengths, by how long the SAME pull keeps going — not by how strong it is:
  - Soft leash: the pull is still going after the soft duration — logged for investigation.
  - Hard leash: the same pull is still going after the longer hard duration — flagged, entering the normal escalation chain (self-check → orchestrator → EDEN). No parallel path. The reasoning: give it a chance to settle; only escalate if it doesn't go away on its own.
- A soft pull that settles back to normal before reaching hard is logged for investigation, and the channel returns to NOMINAL — it does not stay latched. The item, with its readings, is announced on the bus for CHESTER to watch over (agents announce; CHESTER keeps watch — see CHESTER). Exception: a channel already part of an active major fault — its own level FAULT latched, or linked to one via the rule book — stays with that fault's handling and latch, and is not handed off.
- Level FAULT and hard leash still latch until cleared through the sign-off rules — unchanged.
- Context-gated: when a related agent reports an expected cause (as defined in the rule book, e.g. ETHAN in a burn), the leash on the affected readings is loosened — downgrading a hard pull to soft. Loosened still means logged, never silenced.
- Loosening one agent's leash never hides another agent's problem: when GRACIE's temperature leash loosens because ETHAN is burning, ETHAN's own engine leash stays tight, so a real engine overheat is still caught by ETHAN (consistent with ETHAN's inverse rule: a confirmed engine-caused rise is raised).
- Each agent owns the leashes for its own sensors.
- One slope limit per channel, a soft duration and a longer hard duration, and the slack, all come from each channel's rule book. No default values.
- Ageing line: each sensor's expected ageing rate comes from the
  average lifespan of similar parts on similar missions, set per
  craft in the blueprint (see Blueprint). Long-term drift is judged
  against that expected ageing — within the expected rate is ageing,
  faster or accelerating is flagged (see Ageing). The leash itself
  stays for drift over minutes to hours; ageing is the slower,
  separate process covering years.
- Status: GRACIE — built, on her own channels (`agents/gracie.py`): soft and hard by duration; hard latches until cleared through the sign-off rules, soft clears itself and returns to NOMINAL if the pull settles back, announced for CHESTER either way, and CHESTER (built) does watch it. Context-gating is **not built** — it needs an expected-cause signal from another agent GRACIE doesn't have yet. Everyone else — **not built**.

---

## Blueprint (stack-wide)

- Each craft's rule book grows into a full blueprint: for every
  sensor, what it measures, its units, its calibration, its normal
  noise, known interference from other sensors or systems (for
  example, "when the battery switches, these sensors jitter"), sensors
  that legitimately read zero in some conditions (for example, light
  sensors in Earth's shadow), and its expected ageing (see Ageing).
  The blueprint comes from the people who built the craft.
- An agent with no blueprint is a driver in an unfamiliar van with no
  manual: it can still watch for readings outside a safe range, but it
  has no way to tell expected noise, known interference, or an
  expected zero, from something genuinely wrong.
- Noise filter, driven by the blueprint: filters only what the
  blueprint explains as natural noise or known interference between
  sensors or systems. Logs everything it filters — nothing is
  silently dropped. Raw readings are always kept, unfiltered,
  alongside the filtered view. A filter must never hide a real fault:
  anything the blueprint doesn't explain passes through untouched.
- Status: not built.

---

## Ageing

- Components age, so "normal" shifts over a long mission (e.g. solar output falls, battery voltage shifts, coatings change the craft's thermal behaviour; identical parts can age at different rates depending on where they're mounted).
- Each sensor's expected ageing rate comes from the average lifespan
  of similar parts on similar missions, set per craft in the blueprint
  (see Blueprint). No default values.
- Long-term drift is compared against that expected ageing:
  - within the expected rate: logged as ageing (CHESTER tracks it).
  - faster than expected: flagged.
  - ageing that speeds up: flagged.
- Ageing is gradual and sustained; faults are sudden. Limits are recalibrated from long, steady trends, never from spikes.
- Two baselines per sensor: a current baseline, used for alerts, and a historical baseline, for the craft's lifecycle. Updating the current baseline never overwrites the historical one.
- When a sensor is confirmed as ageing, its rule book is updated from that point, ONLY with a human sign-off. The system never moves its own goalposts.
- CHESTER owns long-term ageing tracking and the historical baseline, since that's memory over time.
- Status: **not built**.

---

## Cross-referencing principle

Never judge in isolation. Each agent checks its own domain against the wider picture. GRACIE correlates a rise against what the ship is doing. ETHAN correlates his engine reading against GRACIE's. LUNAE correlates other agents' faults against her own instructions. A deep health sweep (see GRACIE) runs ship-wide, every agent sweeping its own domain, when a stream of small faults suggests something bigger. A rate-of-change jump is cross-checked the same way (see "Rate-of-change sense (stack-wide)"). A leash's context-gating works the same way — checking the wider picture before deciding how tightly to react (see "Leash — drift sense (stack-wide)").

---

## Known exceptions

- **ETHAN** skips the normal orchestrator retry ladder for "I need a human now" and critical malfunctions. Deliberate, and documented as an exception. The bypass is logged to the orchestrator (see above). This changes speed, not rules — the bypass is still logged, still leaves a note, and still needs signing off (see General principles).

---

## Open items (not yet specified)

- Real numbers for every threshold currently written as "safe threshold", "margin", "X amount" or "a set time". Need hardware data.
- Assumptions list: what the system takes for granted without checking. Complete as of 22 October 2026 — see `ASSUMPTIONS.md`.
- Formal specification and verification approach. Partner work.
- Assurance case approach. Partner work.

---

## Wiring plan and ghost mode

- The raising agent classifies its own fault as major or non-urgent, from its rule book. Unknown means major.
- GRACIE fixes and logs her own warnings. Only faults go to the orchestrator.
- Ghost mode: the old wiring keeps control of the ship. The orchestrator sees the same real traffic, questions the old system, and logs what it would have done, even when it disagrees.
- Ghost mode has its own temporary log, archived permanently once the orchestrator takes over.
- Handover criterion: every difference between the old wiring and the orchestrator is explained. Jay reviews the comparison and decides when the orchestrator takes control.
- Wiring order: GRACIE, EDEN, ETHAN, LUNAE, then HALIA and SystemCoordinator.
- Status: GRACIE — built, wired in ghost mode (`agents/ghost_mode.py`). Ghost mode only; the orchestrator does not control anything yet, and does not yet run an independent second check on GRACIE's faults (no real rule data exists — see that file's module docstring). EDEN, ETHAN, LUNAE, HALIA, SystemCoordinator — **not built**.

---

## Real-data testing

We can't make the data do what we want; we need to do what the data wants.

- Three public, labelled datasets, in order: ESA OPS-SAT (OPSSAT-AD), NASA SMAP/MSL, then ESA-ADB.
- Honest limit: public data is anonymised and scaled, so the test is of GRACIE's detection logic, not of true temperature or radiation monitoring. These datasets are anonymised, so no real blueprint exists for them (see Blueprint) — results on them are GRACIE's floor, not her real ability, and every write-up says so.
- Pass means an honest scorecard (faults caught, faults missed, false alarms), not a target score. Written up as "first tests against real spacecraft data", not "validated".
- Counting rule: every counting and scoring choice (per-sample vs.
  per-day vs. per-episode, which window counts as a catch, and so on)
  is fixed before looking at results. Where there's more than one
  fair way to count, the write-up reports all of them, never only the
  nicer one.
- Expected result: sudden spikes caught, slow drift missed. That finding justifies the drift-detection work.
- ESA-ADB is large. The laptop has 6 GB of memory, so read it in chunks, start with one mission and a handful of channels, and expect slow runs.
- Do not commit raw data to the repo. Use a download script, and cite every dataset properly.
- Once GRACIE is wired, run the same data through ghost mode too.
- Status: **not built**.

---

## Build gap summary

Every component above is marked **not built** or partly built. The current code is a skeleton of the philosophy. This spec describes the intended system.
