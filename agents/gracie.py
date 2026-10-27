# agents/gracie.py
# Rewritten 2026-10-25 — any-sensor upgrade. Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""GRACIE — health monitor. Rewritten from the old fixed temp_c/
radiation, AND-condition scaffolding to SPEC.md's any-sensor design:
any set of channels, driven by a rule book (agents/gracie_rulebook.py),
each judged independently against her three senses (level, jump,
leash).

Interpretive calls made, agreed with Jay before building (see
"Ccode update.txt" history):

1. The legacy "system_health" field (NOMINAL/WARNING/FAULT) that EDEN,
   SystemCoordinator and ghost mode all key off is UNCHANGED in shape
   and meaning. It's now a worst-case roll-up across every channel:
   any channel FLAGGED (level crossed, or a leash pull that reached
   its hard duration) -> FAULT; any channel LOGGED (a jump this
   cycle, or a leash pull that reached its soft duration) -> WARNING;
   otherwise NOMINAL. None of EDEN/SystemCoordinator/ghost mode are
   touched by this change.
2. Input is a new, GRACIE-specific shape -- process_readings(readings,
   timestamp), readings a plain {channel_name: value} dict -- not the
   shared TelemetryPacket LUNAE also consumes. Checked directly: LUNAE
   only reads system_health/nav_state/timestamp off that packet, never
   temp_c or radiation, so core/schemas.py and LUNAE are untouched.
3. Level and leash LATCH per channel (persist until clear_fault),
   same discipline the old single FAULT latch already had. Jump does
   NOT latch -- SPEC.md describes it as a momentary "spike" event
   ("logged for investigation immediately"), not an ongoing condition,
   and uncorroborated jump (the only kind GRACIE can judge alone,
   point 7 below) can only ever reach "logged for investigation" --
   never "flagged" -- same vocabulary already used for the jump check
   in real_data_tests/opssat_ad/run_opssat_ad_test.py.
4. "Fires once at the moment of transition" (agreed answer to
   ambiguity 5) means the TRANSITION itself is logged once, not
   re-logged every cycle while a pull continues -- but the LATCHED
   severity it sets still persists in every report until cleared,
   exactly like today's FAULT latch. CHESTER's (not built yet) job is
   the recurring reminder; GRACIE doesn't duplicate it.
5. Jump and leash are rewritten here as INCREMENTAL, stateful
   per-channel trackers -- a bounded rolling window of recent
   (timestamp, value) pairs, plus a running "how long has this pull
   lasted" clock -- rather than the batch, whole-fragment-array logic
   in run_opssat_ad_test.py / simulated_tests/leash_drift/. Same
   underlying maths (see _update_window_and_get_slope's docstring for
   exactly how it reproduces the batch windowed-slope calculation
   step for step); proven equivalent in agents/gracie_equivalence_test.py.
6. clear_fault(channel=None): omitted channel clears every channel's
   latch (preserves the old no-argument call shape); a given channel
   clears only that one.
7. Jump's cross-check (did a related channel/agent also move) and
   leash's context-gating (an expected cause from another agent) are
   NOT implemented here -- both need other agents' signals GRACIE
   doesn't have access to yet. Out of scope until those agents are
   wired in, same order as the rest of SPEC.md's wiring plan.
8. Every report (every cycle, NOMINAL included, same as always)
   carries a "readings" key: per channel, its value, units, and its
   current level/leash latch plus whether it jumped this cycle --
   resolving SPEC.md's open item that GRACIE's reports should carry
   the actual readings, not just the aggregate state.
9. Added 2026-10-25 (same day, second pass): a soft leash pull that
   settles back to normal before reaching hard no longer leaves the
   channel stuck at WARNING. It's announced on "chester/watch" (with
   the current readings) for CHESTER to pick up -- SPEC.md's "agents
   announce; CHESTER keeps watch" -- and the channel's latch clears to
   NOMINAL itself. Exception: a channel already part of an active
   major fault (its own level FAULT latched, or linked to one via
   ChannelRule.linked_channels) stays with that fault's latch instead
   -- not handed off, not cleared. Hard leash and level FAULT are
   unchanged: both still latch until an explicit clear_fault, same as
   before.
10. Added 2026-10-25 (third pass, CHESTER now being built): GRACIE
    announces more on "chester/watch", not just a settled leash pull --
    every jump event, and every time a channel enters or leaves
    WARNING (by any means: a leash soft transition entering it, or
    leaving it by settling, escalating to hard, or an explicit
    clear_fault). Same once-per-transition rule throughout -- no
    repeat announcements for a condition that's still ongoing. None of
    this changes any verdict or latching; it only adds more kinds of
    announcement alongside the existing "leash_settled" one. Proven
    not to change any equivalence result in gracie_equivalence_test.py.
11. Added 2026-10-25 (fourth pass, ESA-ADB follow-up run):
    clear_fault(channel=None, reset_leash_timer=True) -- the default
    preserves the original behaviour exactly for every existing
    caller (clearing the latch also resets the leash's pull-duration
    clock and edge-detectors). Pass reset_leash_timer=False to clear
    only the latch, leaving an ongoing pull's clock running -- for a
    periodic stand-in sign-off (e.g. once per day over a multi-year
    recording) where resetting the latch shouldn't also erase a pull
    that's been building for longer than the clear interval. Found
    while running real_data_tests/esa_adb/'s first pass (see that
    folder's RESULTS.md) -- the daily clear_fault() there was
    silently preventing any drift from ever reaching hard duration if
    it needed to straddle a day boundary to get there.
12. Added 2026-10-26 (ESA-ADB context-checking round) -- two small,
    additive changes to LEVEL only, each justified directly against a
    SPEC.md line, built as minimally as possible per Jay's "keep the
    agents lean" rule (real_data_tests/esa_adb/'s own timing-
    correlation and command/event linking stays entirely in
    real_data_tests/, never here):
    - New crossing while already latched (SPEC.md GRACIE section): a
      level crossing that starts again after dropping back below
      threshold, while the channel is STILL latched FAULT from an
      earlier crossing, now gets its own fresh log line. The latch
      itself is untouched -- same FAULT severity as before, nothing
      reset, nothing released. Pure traceability for ASSUMPTIONS.md
      A76 (a false latch silently absorbing a real one); doesn't
      change any verdict.
    - Expected-cause input (SPEC.md GRACIE section: "Expected causes
      ... are logged. No explanation ... flagged as an early
      warning."): process_readings() takes an optional
      `expected_causes` set of channel names. A level crossing on a
      named channel is LOGGED (WARNING, same vocabulary as jump/soft
      leash) instead of FLAGGED (FAULT) -- except it never downgrades
      an existing FAULT latch, preserving the one-way-ratchet rule
      used everywhere else in this file. GRACIE has no idea what an
      "expected cause" actually is or where it comes from -- that's
      deliberately out of scope here; real_data_tests/esa_adb/ decides
      which channels have one, from training-only command/event
      timing correlation, and simply passes the set in.
13. Added 2026-10-27 (Item 3b, driven by the simulated craft's
    findings -- see sim/RESULTS.md and Ccode update.txt), three
    changes, each justified against a specific SPEC.md GRACIE line:
    - Expected causes now carry a size (SPEC.md: "An expected cause
      ... carries the blueprint's expected size ... with the
      blueprint's own tolerance ... A rise inside an expected cause's
      active window but outside its expected size is not excused").
      `expected_causes` is now `{channel: (low, high) or None}` --
      None preserves point 12's original behaviour exactly (a cause
      was commanded, no known size, any value in that cause's window
      is excused) for real_data_tests/esa_adb/'s correlation-based
      usage, which genuinely can't claim to know a size. A (low, high)
      tuple means the caller DOES know the blueprint's expected size
      (the simulated craft, from its own blueprint) -- a value outside
      it is treated as NOT excused, flagged the same as an unexplained
      crossing, even though a cause was commanded.
    - New crossing while already latched now reaches the orchestrator
      (SPEC.md: "that is reported as a fresh event in its own right,
      through the normal escalation chain to the orchestrator"). One
      new call: this branch now also announces "new_crossing_while_
      latched" on chester/watch (she already announces other kinds;
      this is simply one more). The latch itself is untouched by this
      -- nothing released, nothing reset. A new, separate, small file
      (agents/escalation_watch.py) listens for this specific kind and
      forwards it to the orchestrator -- a STAND-IN wiring, not GRACIE
      calling the orchestrator directly, same architecture as every
      other agent-to-agent path in this codebase today.
    - Stillness, a fourth sense (SPEC.md: "If a sensor's variation
      over that window falls below its blueprint-stated minimum, the
      sensor itself is suspect ... GRACIE flags it as a sensor-health
      fault, independently of level/jump/leash"). Two new required
      ChannelRule fields, stuck_window_seconds/min_normal_noise (no
      defaults -- min_normal_noise<=0.0 is the explicit, stated way a
      caller disables this check for a channel, not an invented real
      number); allow_steady exempts a channel entirely. Tagged
      DISTINCTLY from an ordinary level/leash fault, in the log line
      ("sensor suspect: X frozen", not "X fault") and in the report
      (`sensor_health_fault` alongside `severity`), so a reader can
      tell the instrument is in question, not the quantity it
      measures. Latches exactly like level (one-way ratchet, only
      clear_fault releases it) -- participates in the same
      `latched_severity`/`health_state` rollup by construction, since
      it sets the same field everything else does.

No invented numbers: every ChannelRule field is required, no
defaults (see agents/gracie_rulebook.py). Real callers and tests alike
must supply real or clearly-labelled fixture values.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

from core.bus import EventBus
from core.logger import setup_agent_logger
from agents.gracie_rulebook import ChannelRule, RuleBook

# Severity ranks for the worst-case roll-up -- matches the legacy
# system_health vocabulary EDEN/SystemCoordinator/ghost mode already
# expect. "LOGGED" (jump, soft leash) maps to WARNING; "FLAGGED"
# (level, hard leash) maps to FAULT -- see module docstring, point 1.
_SEVERITY_RANK = {"NOMINAL": 0, "WARNING": 1, "FAULT": 2}

# Sentinel distinguishing "this channel has no entry in expected_causes
# at all" from "it has an entry whose value is None" (point 13 above --
# None is itself a meaningful value, "a cause was commanded, size
# unknown," not the same as "no cause was commanded").
_NO_EXPECTED_CAUSE = object()


@dataclass
class _ChannelState:
    rule: ChannelRule
    latched_severity: str = "NOMINAL"  # level + leash latch; clear_fault resets it
    last_sample: Optional[Tuple[float, float]] = None  # (timestamp, value), for jump
    window: Deque[Tuple[float, float]] = field(default_factory=deque)  # for leash's windowed slope
    pull_run_start: Optional[float] = None  # leash's "how long has this pull lasted" clock
    # Edge-detectors for the CURRENT pull specifically -- reset to False
    # whenever the pull itself drops below the limit (same per-episode
    # edge-triggering as the batch scripts' find_pull_episodes()).
    # Deliberately separate from latched_severity: latched_severity is
    # a one-way ratchet that only clear_fault can undo, so a channel
    # already latched FAULT from an earlier pull would otherwise hide
    # whether a *later, independent* pull also reached soft/hard --
    # which matters for comparing against the batch scripts (which
    # have no latching concept at all) in gracie_equivalence_test.py.
    soft_active: bool = False
    hard_active: bool = False
    # Edge-detector for LEVEL specifically -- lets a new, separate
    # crossing (value dips back in bounds, then crosses again) be
    # logged in its own right even while latched_severity is still
    # FAULT from an earlier crossing (module docstring, point 12).
    level_crossing_active: bool = False
    # Stillness (point 13): a sliding window of recent (timestamp,
    # value) pairs, same incremental-and-trimmed shape as leash's own
    # `window` above, but kept separate since the two senses cover
    # different durations and leash's anchor-only trim can't answer
    # "what's the full range over this window" the way Stillness
    # needs. True from the moment Stillness first triggers until
    # clear_fault -- the "sensor suspect" tag on the report, tracked
    # separately from latched_severity so a reader can tell the
    # instrument is in question, not the quantity it measures.
    stillness_window: Deque[Tuple[float, float]] = field(default_factory=deque)
    stillness_active: bool = False


class GracieAgent:
    def __init__(self, bus: EventBus, rule_book: RuleBook):
        self.logger = setup_agent_logger("gracie")
        self.bus = bus
        self.rule_book = rule_book
        self._states: Dict[str, _ChannelState] = {
            name: _ChannelState(rule=rule) for name, rule in rule_book.items()
        }
        self.health_state = "NOMINAL"
        self._last_readings: Dict[str, dict] = {}
        self.bus.subscribe("gracie/command", self.on_command)

    # --- commands -----------------------------------------------------
    def on_command(self, payload):
        command = payload.get("command")
        self.logger.info(f"Received command: {command} with payload {payload}")
        if command == "run_diagnostics":
            self.report_health()
        elif command == "clear_fault":
            self.clear_fault(payload.get("channel"))

    def clear_fault(self, channel: Optional[str] = None, reset_leash_timer: bool = True):
        """Clears one channel's latch, or every channel's if `channel`
        is omitted -- preserves the old no-argument call shape.

        `reset_leash_timer` defaults to True, preserving exactly the
        original behaviour for every existing caller: clearing the
        latch also resets the leash's "how long has this pull lasted"
        clock and its soft/hard edge-detectors. Pass False to clear
        only the latch and leave the leash timer running -- for a
        periodic stand-in sign-off (e.g. once per day, in a long
        real-data test) where resetting the latch shouldn't also
        erase a pull that's been building for longer than the clear
        interval. Added for real_data_tests/esa_adb/'s daily
        clear_fault() calls, which found this gap: see that folder's
        RESULTS.md."""
        timestamp = int(time.time())
        channels = [channel] if channel is not None else list(self._states.keys())
        for ch in channels:
            state = self._states.get(ch)
            if state is None:
                continue
            prior_severity = state.latched_severity
            state.latched_severity = "NOMINAL"
            state.stillness_active = False
            if reset_leash_timer:
                state.pull_run_start = None
                state.soft_active = False
                state.hard_active = False
            if ch in self._last_readings:
                self._last_readings[ch]["severity"] = "NOMINAL"
                self._last_readings[ch]["sensor_health_fault"] = False
            self._announce_warning_transition(ch, timestamp, prior_severity, "NOMINAL")
        self.logger.info(f"Cleared fault for {channel if channel else 'all channels'}")
        self._recompute_aggregate()
        self.report_health(timestamp)

    # --- the three senses, per channel --------------------------------
    def _process_level(self, channel: str, state: _ChannelState, value: float,
                        timestamp: float, expected_cause=_NO_EXPECTED_CAUSE):
        """`expected_cause` -- SPEC.md GRACIE section: "An expected
        cause ... carries the blueprint's expected size ... with the
        blueprint's own tolerance ... A rise inside an expected cause's
        active window but outside its expected size is not excused."
        GRACIE herself has no idea what counts as an expected cause or
        where it comes from; the caller decides (module docstring,
        point 12/13). Three states, via the `_NO_EXPECTED_CAUSE`
        sentinel default: no entry at all (not expected); an entry of
        None (a cause was commanded, size unknown -- excuses any
        value, point 12's original behaviour, preserved exactly); an
        entry of (low, high) (a cause was commanded with a known
        expected size -- excuses only a value actually inside it). A
        crossing that IS excused is LOGGED (WARNING) and never
        downgrades an existing FAULT latch -- the one-way-ratchet rule
        everywhere else in this file."""
        rule = state.rule
        crossing = value > rule.level_high or value < rule.level_low
        if not crossing:
            state.level_crossing_active = False
            return
        is_new_crossing = not state.level_crossing_active
        has_expected_cause = expected_cause is not _NO_EXPECTED_CAUSE
        matches_expected = has_expected_cause and (
            expected_cause is None or (expected_cause[0] <= value <= expected_cause[1])
        )
        if matches_expected:
            if is_new_crossing:
                self.logger.info(
                    f"{channel}: LEVEL crossing with expected cause -- logged, not flagged "
                    f"(value={value}{rule.units}, high={rule.level_high}, low={rule.level_low})"
                )
            if _SEVERITY_RANK[state.latched_severity] < _SEVERITY_RANK["WARNING"]:
                state.latched_severity = "WARNING"
            state.level_crossing_active = True
            return
        if is_new_crossing:
            if state.latched_severity != "FAULT":
                self.logger.info(
                    f"{channel}: LEVEL transition -> FAULT "
                    f"(value={value}{rule.units}, high={rule.level_high}, low={rule.level_low})"
                )
            else:
                self.logger.info(
                    f"{channel}: LEVEL crossing while already latched FAULT -- new event "
                    f"(value={value}{rule.units}, high={rule.level_high}, low={rule.level_low})"
                )
                # Point 13: reported through to the orchestrator (via
                # agents/escalation_watch.py's stand-in wiring), not
                # just logged -- the latch itself is untouched by this.
                self._announce_for_chester(channel, timestamp, "new_crossing_while_latched")
        state.latched_severity = "FAULT"
        state.level_crossing_active = True

    def _process_stillness(self, channel: str, state: _ChannelState, timestamp: float,
                            value: float) -> bool:
        """SPEC.md GRACIE section, "Stillness": a sensor's variation
        over `rule.stuck_window_seconds` must never fall below
        `rule.min_normal_noise`, or the sensor itself is suspect.
        `min_normal_noise<=0.0` (or `allow_steady`) is the explicit,
        stated way a caller disables this for a channel -- checked
        FIRST, before any window bookkeeping, both because a disabled
        check can never fire either way and because every real-data
        test harness in this repo disables it this round (see
        agents/gracie_rulebook.py) and would otherwise pay an
        O(window size) cost on every single sample for nothing across
        millions of real readings.

        Unlike leash's window (which only ever needs its two
        endpoints to get a slope), Stillness needs the actual spread
        of every value in the window, so it keeps its own deque,
        trimmed the same incremental way -- oldest entries dropped
        once they age out of `stuck_window_seconds` -- rather than
        reusing leash's anchor-only trim."""
        rule = state.rule
        if rule.allow_steady or rule.min_normal_noise <= 0.0:
            return False
        window = state.stillness_window
        window.append((timestamp, value))
        while window and (timestamp - window[0][0]) > rule.stuck_window_seconds:
            window.popleft()
        if (timestamp - window[0][0]) < rule.stuck_window_seconds:
            return False  # window doesn't cover the full stated duration yet
        values = [v for _, v in window]
        return (max(values) - min(values)) < rule.min_normal_noise

    def _process_jump(self, state: _ChannelState, timestamp: float, value: float) -> bool:
        """True if the rate since the last sample exceeds the jump
        limit -- a momentary event, never latched (see module
        docstring, point 3)."""
        if state.last_sample is None:
            state.last_sample = (timestamp, value)
            return False
        last_t, last_v = state.last_sample
        state.last_sample = (timestamp, value)
        dt = timestamp - last_t
        if dt == 0:
            return False
        return abs(value - last_v) / dt > state.rule.jump_limit

    def _update_window_and_get_slope(self, state: _ChannelState, timestamp: float, value: float) -> Optional[float]:
        """Incremental equivalent of run_opssat_ad_test.py's
        Fragment._windowed_slopes(): the window deque's oldest entry
        is always the TIGHTEST valid anchor -- the same point that
        script's two-pointer `j` would be at, for the same reason
        (pop from the left only while the *next* entry is still at
        least leash_window_seconds away from `timestamp`). Proven
        equivalent in agents/gracie_equivalence_test.py."""
        window = state.window
        while len(window) >= 2 and (timestamp - window[1][0]) >= state.rule.leash_window_seconds:
            window.popleft()
        window.append((timestamp, value))
        anchor_t, anchor_v = window[0]
        dt = timestamp - anchor_t
        if dt >= state.rule.leash_window_seconds:
            return (value - anchor_v) / dt
        return None

    def _is_part_of_active_major_fault(self, state: _ChannelState) -> bool:
        """This channel's own level FAULT is latched, or it's linked
        (ChannelRule.linked_channels) to another channel currently
        latched FAULT -- either way, a settling soft pull here stays
        with that fault's handling rather than clearing itself."""
        if state.latched_severity == "FAULT":
            return True
        return any(
            (linked_state := self._states.get(linked)) is not None
            and linked_state.latched_severity == "FAULT"
            for linked in state.rule.linked_channels
        )

    def _process_leash(self, channel: str, state: _ChannelState, timestamp: float,
                        slope: Optional[float]) -> Optional[str]:
        """Soft and hard are checked independently each cycle (not
        mutually exclusive) so a pull that keeps going produces both
        transitions, each at its own correct timestamp -- matching
        the batch scorer's separate soft/hard episode detection.
        soft_active/hard_active edge-trigger per pull (reset when the
        pull itself ends); latched_severity only ever ratchets up on
        its own, and only clear_fault resets it -- EXCEPT a soft-only
        pull settling back, which clears itself (module docstring,
        point 9) unless the channel is part of an active major fault.
        Returns "settled" when the caller should announce for CHESTER,
        otherwise None."""
        rule = state.rule
        if slope is None or abs(slope) <= rule.leash_slope_limit:
            was_soft_only = state.soft_active and not state.hard_active
            state.pull_run_start = None
            state.soft_active = False
            state.hard_active = False
            if not was_soft_only:
                return None
            if self._is_part_of_active_major_fault(state):
                self.logger.info(
                    f"{channel}: soft leash pull settled, but the channel is part of "
                    f"an active major fault -- staying latched, not handed off to CHESTER"
                )
                return None
            self.logger.info(f"{channel}: soft leash pull settled back to NOMINAL -- announcing for CHESTER")
            state.latched_severity = "NOMINAL"
            return "settled"

        if state.pull_run_start is None:
            state.pull_run_start = timestamp
        elapsed = timestamp - state.pull_run_start

        if elapsed >= rule.leash_soft_duration_seconds and not state.soft_active:
            state.soft_active = True
            self.logger.info(f"{channel}: LEASH SOFT transition at t={timestamp} (slope={slope:.6g})")
            if _SEVERITY_RANK[state.latched_severity] < _SEVERITY_RANK["WARNING"]:
                state.latched_severity = "WARNING"
        if elapsed >= rule.leash_hard_duration_seconds and not state.hard_active:
            state.hard_active = True
            self.logger.info(f"{channel}: LEASH HARD transition at t={timestamp} (slope={slope:.6g})")
            if _SEVERITY_RANK[state.latched_severity] < _SEVERITY_RANK["FAULT"]:
                state.latched_severity = "FAULT"
        return None

    # --- main entry point ----------------------------------------------
    def process_readings(self, readings: Dict[str, float], timestamp: float,
                          expected_causes: Optional[Dict[str, Optional[Tuple[float, float]]]] = None):
        """readings: {channel_name: value}. Channels not in the rule
        book are logged and ignored -- no guessing at a channel GRACIE
        has no rule for.

        expected_causes: optional {channel: (expected_low, expected_high)
        or None} -- a context-provided expected cause THIS cycle
        (module docstring, points 12/13). None preserves point 12's
        original behaviour (a cause was commanded, size unknown, any
        value is excused); a (low, high) tuple only excuses a value
        actually inside it (point 13 -- "not excused by that cause"
        otherwise). Omitted or empty preserves the original behaviour
        exactly for every existing caller."""
        cycle_jump_channels = set()
        expected_causes = expected_causes or {}

        for channel, value in readings.items():
            state = self._states.get(channel)
            if state is None:
                self.logger.warning(
                    f"Reading for unrecognized channel '{channel}' -- no rule book entry, ignored."
                )
                continue
            rule = state.rule
            prior_severity = state.latched_severity

            expected_cause = expected_causes.get(channel, _NO_EXPECTED_CAUSE)
            self._process_level(channel, state, value, timestamp, expected_cause=expected_cause)
            jump_event = self._process_jump(state, timestamp, value)
            slope = self._update_window_and_get_slope(state, timestamp, value)
            leash_event = self._process_leash(channel, state, timestamp, slope)
            is_stuck = self._process_stillness(channel, state, timestamp, value)
            if is_stuck:
                if not state.stillness_active:
                    self.logger.info(
                        f"sensor suspect: {channel} frozen (variation over "
                        f"{rule.stuck_window_seconds:.0f}s below blueprint minimum "
                        f"{rule.min_normal_noise}{rule.units})"
                    )
                state.stillness_active = True
                state.latched_severity = "FAULT"

            if jump_event:
                cycle_jump_channels.add(channel)
                self.logger.info(f"{channel}: JUMP event (value={value}{rule.units})")

            self._last_readings[channel] = {
                "value": value,
                "units": rule.units,
                "severity": state.latched_severity,
                "jump": jump_event,
                "sensor_health_fault": state.stillness_active,
            }

            if jump_event:
                self._announce_for_chester(channel, timestamp, "jump")
            if leash_event == "settled":
                self._announce_for_chester(channel, timestamp, "leash_settled")
            self._announce_warning_transition(channel, timestamp, prior_severity, state.latched_severity)

        self._recompute_aggregate(cycle_jump_channels)
        self.report_health(timestamp)

    def _recompute_aggregate(self, cycle_jump_channels=frozenset()):
        """Worst case across every known channel -- not just the ones
        in this cycle's readings, since a channel's latch persists
        even on a cycle where it wasn't sampled."""
        worst = "NOMINAL"
        for channel, state in self._states.items():
            severity = state.latched_severity
            if channel in cycle_jump_channels and _SEVERITY_RANK[severity] < _SEVERITY_RANK["WARNING"]:
                severity = "WARNING"
            if _SEVERITY_RANK[severity] > _SEVERITY_RANK[worst]:
                worst = severity
        self.health_state = worst
        return worst

    def _announce_warning_transition(self, channel: str, timestamp: float,
                                      prior_severity: str, new_severity: str):
        """Fires once per transition, either direction -- regardless of
        which sense caused it (today, only leash soft/hard/settle and
        clear_fault ever change latched_severity to or from WARNING)."""
        if prior_severity != "WARNING" and new_severity == "WARNING":
            self._announce_for_chester(channel, timestamp, "warning_entered")
        elif prior_severity == "WARNING" and new_severity != "WARNING":
            self._announce_for_chester(channel, timestamp, "warning_left")

    def _announce_for_chester(self, channel: str, timestamp: float, kind: str):
        """SPEC.md: "Agents announce their own faults and anomalies on
        the bus; CHESTER keeps watch over them." `kind` is one of
        "jump", "warning_entered", "warning_left", "leash_settled"."""
        self.logger.info(f"{channel}: announcing '{kind}' on chester/watch")
        self.bus.publish("chester/watch", {
            "kind": kind,
            "agent": "GRACIE",
            "channel": channel,
            "timestamp": timestamp,
            "readings": dict(self._last_readings),
        })

    def report_health(self, timestamp=None):
        if timestamp is None:
            timestamp = int(time.time())
        self.logger.info(f"Reporting health: {self.health_state}")
        self.bus.publish("telemetry/health", {
            "system_health": self.health_state,
            "source": "GRACIE",
            "timestamp": timestamp,
            "readings": dict(self._last_readings),
        })
