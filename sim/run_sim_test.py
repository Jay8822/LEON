# sim/run_sim_test.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Runs the simulated LEON craft's faulted timeline through every
currently-built, currently-wired agent, TWICE (Jay's approved change
2): once with GRACIE's `expected_causes` always empty (she gets no
help from the craft's own plan) and once with the real per-sample
expected-cause sets the craft's own event schedule implies, fed
through her existing input -- same seed, same faults, same frozen
rule book both times, so the value of knowing the plan is measured,
not assumed.

ONE shared craft, not nine separate mini-harnesses: a single
EventBus, a single GracieAgent holding all nine channels (her real
design already supports a multi-channel rule book -- see
agents/gracie.py), a single EdenAgent/EscalationOrchestrator/
ChesterAgent/GhostModeHarness, and EthanAgent/LunaeAgent run exactly
as they are. This is more realistic than nine isolated channels (EDEN
only ever sees GRACIE's aggregate `system_health`, so a FAULT on any
one channel triggers the same real SAFE_MODE reaction a real craft
would see) and is what "exercise the full chain" (approved plan)
actually means.

GhostModeHarness (agents/ghost_mode.py) is reused exactly as it
already exists -- not rebuilt -- for the "orchestrator ->
EDEN/sign-off" leg: it already does precisely this (compare EDEN's
real reaction against what EscalationOrchestrator would have
decided), and its own module docstring already names the real,
narrow scope of what it does and doesn't cover (no rerun ladder, no
sign-off machinery -- none of that has anything to attach to without
real per-agent threshold data, same as today).

EscalationOrchestrator's own `eden_rules`/`own_rules` are empty dicts
here -- `decide()` (which GhostModeHarness calls) never consults them;
only `triage()` does, and ghost mode explicitly skips triage() by its
own documented design. `major_fault_window_seconds` /
`non_urgent_fault_window_seconds` / `light_flag_cycle_minutes` are
simulation test-fixture values (SPEC.md: "to be set from hardware
data, no default"), matched to this sim's own leash durations for
consistency, not claimed as real spacecraft numbers.

ISOLATION IS DEFERRED, NOT SCORED (approved plan): the Diagnostic
checklist doesn't exist yet. This only scores DETECTION (flagged or
not, and detection delay) and FALSE ALARMS, for every planted fault
and every normal event, in both runs.

EthanAgent/LunaeAgent run exactly as they currently are -- their
current simple mode/nav-state reporting only, never upgraded to
consume this sim's actual thrust/fuel_flow/velocity/attitude_rate
values in any detailed way. That gap is real and is stated plainly in
sim/RESULTS.md, not glossed over.
"""
import json
import os

from agents.chester import ChesterAgent
from agents.eden import EdenAgent
from agents.escalation_orchestrator import EscalationOrchestrator
from agents.ethan_ai import EthanAgent
from agents.ghost_mode import GhostModeHarness
from agents.gracie import GracieAgent
from agents.lunae import LunaeAgent
from core.bus import EventBus

from sim.craft import build_clean_timeline, TOTAL_SECONDS, _kick_offset
from sim.fault_injection import inject_faults
from sim.human_signoff import HumanSignoff
from sim.rulebook import build_rule_book

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

# Simulation test-fixture values for EscalationOrchestrator/CHESTER --
# matched to this sim's own leash durations for consistency, not real
# spacecraft numbers (see module docstring).
MAJOR_FAULT_WINDOW_SECONDS = 150.0
NON_URGENT_FAULT_WINDOW_SECONDS = 60.0
LIGHT_FLAG_CYCLE_MINUTES = 10.0
CHESTER_REFRESH_PERIOD_SECONDS = 600.0
CHESTER_MAX_LAYERS = 6
# Item 3b, Jay's approved change 6: same scale as CHESTER's own
# refresh period, not a new invented number -- a sim-only "how often
# a human actually checks in" delay, not a real spacecraft parameter.
HUMAN_RESPONSE_DELAY_SECONDS = CHESTER_REFRESH_PERIOD_SECONDS


# Item 3b (Jay's approved change 1): a kick's expected RANGE tracks
# its own ramp/decay shape at this exact second, not a flat range for
# the whole event window -- centered on the actual value GRACIE will
# read, with a tolerance that is generous enough to absorb the
# sensor's own ordinary noise riding on top of a CORRECTLY-sized
# kick, but tight enough to exclude sim/fault_injection.py's
# WRONG_BURN_SCALE=0.25 bad_engine_burn (a 4x difference from the
# normal scale=1.0 kicks -- comfortably outside either tolerance term
# below). The floor term keeps the tolerance meaningful even right at
# the start/end of a ramp, where the kick's own instantaneous offset
# is near zero.
#
# COMMISSIONING FINDING: the expected value must be anchored on the
# channel's ACTUAL reading right before the event starts, not the
# blueprint's fixed nominal baseline. These sensors' noise is an
# unbounded random walk (same reason real-data limits are derived
# from same-length chunks, Correction 1) -- by late in a 21,600s run
# it can have drifted tens of units away from nominal, so "nominal +
# kick shape" alone badly undershot a correctly-sized, late-timeline
# kick's actual expected value, and the real kick was wrongly
# rejected as "outside its expected size." Anchoring on the pre-event
# baseline (the actual reading at start_s-1) correctly separates "the
# kick's own size is right" from "the baseline has drifted," which is
# exactly the distinction this check needs to make.
EXPECTED_KICK_TOLERANCE_FRACTION = 0.4   # x the kick's own peak
EXPECTED_KICK_TOLERANCE_FLOOR_MULTIPLE = 5.0  # x the channel's own jump_limit


def event_baselines(events, values):
    """{event_name: {channel: value right before the event started}}
    -- computed once, not per sample, since it never changes while
    scoring a fixed, already-injected series."""
    baselines = {}
    for ev in events:
        baselines[ev["name"]] = {
            channel: values[channel][max(ev["start_s"] - 1, 0)]
            for channel in ev.get("kick_peaks", {})
        }
    return baselines


def active_expected_causes(events, second_offset, rule_book, baselines):
    """{channel: (low, high) or None} -- per Jay's approved change 1.
    "kick" effects get a real size-checked range tracking the kick's
    own shape, anchored on the channel's actual pre-event baseline
    (see module comment above); "jitter"/"zero" effects keep None (no
    known size to check against, and no wrong-magnitude fault variant
    tests them this round) -- see agents/gracie.py module docstring,
    point 13."""
    active = {}
    for ev in events:
        if not (ev["start_s"] <= second_offset < ev["end_s"]):
            continue
        for channel in ev["affected_channels"]:
            effect = ev["effects"][channel]
            if effect != "kick":
                active[channel] = None
                continue
            peak = ev["kick_peaks"][channel]
            baseline = baselines[ev["name"]][channel]
            offset = _kick_offset(ev["start_s"], ev["duration_s"], peak, second_offset)
            rule = rule_book[channel]
            tolerance = max(
                EXPECTED_KICK_TOLERANCE_FRACTION * abs(peak),
                EXPECTED_KICK_TOLERANCE_FLOOR_MULTIPLE * rule.jump_limit,
            )
            expected_value = baseline + offset
            active[channel] = (expected_value - tolerance, expected_value + tolerance)
    return active


def build_craft(rule_book, faults):
    bus = EventBus()
    gracie = GracieAgent(bus, rule_book)
    eden = EdenAgent(bus)
    bus.subscribe("telemetry/health", eden.on_health_event)
    orchestrator = EscalationOrchestrator(
        eden_rules={}, own_rules={},
        major_fault_window_seconds=MAJOR_FAULT_WINDOW_SECONDS,
        non_urgent_fault_window_seconds=NON_URGENT_FAULT_WINDOW_SECONDS,
        light_flag_cycle_minutes=LIGHT_FLAG_CYCLE_MINUTES,
    )
    chester = ChesterAgent(
        bus, orchestrator,
        refresh_period_seconds=CHESTER_REFRESH_PERIOD_SECONDS,
        max_layers=CHESTER_MAX_LAYERS,
        is_irrelevant=lambda item: False,
    )
    ghost = GhostModeHarness(bus, eden, orchestrator)
    ethan = EthanAgent(bus)
    lunae = LunaeAgent(bus)
    human = HumanSignoff(gracie, orchestrator, faults, HUMAN_RESPONSE_DELAY_SECONDS)
    return {
        "bus": bus, "gracie": gracie, "eden": eden, "orchestrator": orchestrator,
        "chester": chester, "ghost": ghost, "ethan": ethan, "lunae": lunae, "human": human,
    }


def run_scored(rule_book, timestamps, values, events, faults, use_expected_causes):
    craft = build_craft(rule_book, faults)
    gracie = craft["gracie"]
    per_channel_log = {ch: [] for ch in rule_book}
    aggregate_log = []
    start = timestamps[0]
    baselines = event_baselines(events, values) if use_expected_causes else None
    for i, t in enumerate(timestamps):
        second_offset = (t - start).total_seconds()
        readings = {ch: values[ch][i] for ch in rule_book}
        expected = active_expected_causes(events, second_offset, rule_book, baselines) if use_expected_causes else None
        gracie.process_readings(readings, timestamp=t.timestamp(), expected_causes=expected)
        craft["human"].tick(second_offset)  # Item 3b: may clear_fault() a released channel this cycle
        for ch in rule_book:
            last = gracie._last_readings[ch]
            per_channel_log[ch].append({
                "sample_index": i, "severity": last["severity"], "jump_event": bool(last["jump"]),
            })
        aggregate_log.append({
            "sample_index": i, "health_state": gracie.health_state, "eden_status": craft["eden"].status,
        })
    return per_channel_log, aggregate_log, craft


def score_faults(per_channel_log, faults):
    """For each planted fault: first sample index (if any) where its
    channel's severity is WARNING or FAULT at/after the fault's
    start_s -- detection delay in seconds from fault onset. MISSED if
    never flagged before the run ends."""
    results = []
    for f in faults:
        channel = f["channel"].split(",")[0]  # ground-truth primary channel
        log = per_channel_log[channel]
        start_idx = f["start_s"]
        first_flag = None
        for entry in log[start_idx:]:
            if entry["severity"] in ("WARNING", "FAULT"):
                first_flag = entry
                break
        if first_flag is None:
            results.append({"fault": f["name"], "channel": channel, "detected": False,
                             "delay_seconds": None, "severity_at_detection": None})
        else:
            results.append({
                "fault": f["name"], "channel": channel, "detected": True,
                "delay_seconds": first_flag["sample_index"] - start_idx,
                "severity_at_detection": first_flag["severity"],
            })
    return results


def score_false_alarms(per_channel_log, events):
    """For every normal event, for every channel it affects: did that
    channel show FAULT at any point during the event's own window
    (start_s..end_s)? Reported per event/channel, not aggregated away."""
    results = []
    for ev in events:
        for ch in ev["affected_channels"]:
            window = per_channel_log[ch][ev["start_s"]:ev["end_s"]]
            flagged = [e for e in window if e["severity"] == "FAULT"]
            results.append({
                "event": ev["name"], "channel": ch,
                "false_fault_samples": len(flagged),
                "false_alarmed": len(flagged) > 0,
            })
    return results


def score_background_false_alarms(per_channel_log, events, faults, total_seconds):
    """Every FAULT sample on every channel, OUTSIDE any event's or
    fault's own window -- surfaces exactly the kind of baseline false
    alarm sim/COMMISSIONING.md's third finding already found and
    accepted (battery_voltage, fuel_flow), reported here as part of
    the real scored result, not hidden."""
    covered = {}
    for ev in events:
        for ch in ev["affected_channels"]:
            covered.setdefault(ch, []).append((ev["start_s"], ev["end_s"]))
    for f in faults:
        for ch in f["channel"].split(","):
            covered.setdefault(ch, []).append((f["start_s"], f["end_s"]))

    results = {}
    for ch, log in per_channel_log.items():
        windows = covered.get(ch, [])
        count = 0
        first_idx = None
        for entry in log:
            if entry["severity"] != "FAULT":
                continue
            i = entry["sample_index"]
            if any(lo <= i < hi for lo, hi in windows):
                continue
            count += 1
            if first_idx is None:
                first_idx = i
        if count:
            results[ch] = {"background_false_fault_samples": count, "first_sample_index": first_idx}
    return results


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rule_book, blueprint = build_rule_book()
    timestamps, clean_values, events = build_clean_timeline(rule_book, blueprint)
    faulted_values, faults = inject_faults(timestamps, clean_values, rule_book, TOTAL_SECONDS)

    report = {"faults": faults, "events": events, "runs": {}}
    for label, use_expected in (("without_expected_causes", False), ("with_expected_causes", True)):
        print(f"=== Running: {label} ===")
        per_channel_log, aggregate_log, craft = run_scored(
            rule_book, timestamps, faulted_values, events, faults, use_expected
        )
        fault_scores = score_faults(per_channel_log, faults)
        false_alarm_scores = score_false_alarms(per_channel_log, events)
        background = score_background_false_alarms(per_channel_log, events, faults, TOTAL_SECONDS)

        eden_safe_mode_samples = sum(1 for e in aggregate_log if e["eden_status"] == "SAFE_MODE")
        ghost_log = craft["ghost"].comparison_log()
        ghost_disagreements = [g for g in ghost_log if not g["agree"]]

        report["runs"][label] = {
            "fault_detection": fault_scores,
            "false_alarms_on_normal_events": false_alarm_scores,
            "background_false_alarms": background,
            "eden_safe_mode_sample_count": eden_safe_mode_samples,
            "ghost_mode_comparisons": len(ghost_log),
            "ghost_mode_disagreements": len(ghost_disagreements),
        }
        for fs in fault_scores:
            print(" ", fs)
        n_false = sum(1 for a in false_alarm_scores if a["false_alarmed"])
        print(f"  false alarms on normal events: {n_false}/{len(false_alarm_scores)}")
        print(f"  background false alarms (channels): {list(background.keys())}")
        print(f"  EDEN SAFE_MODE samples: {eden_safe_mode_samples}")
        print(f"  ghost mode: {len(ghost_log)} comparisons, {len(ghost_disagreements)} disagreements")

    with open(os.path.join(OUT_DIR, "sim_results.json"), "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nWritten to {os.path.join(OUT_DIR, 'sim_results.json')}")


if __name__ == "__main__":
    main()
