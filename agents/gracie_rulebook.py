# agents/gracie_rulebook.py
# Added 2026-10-25 — Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""GRACIE's rule book: one ChannelRule per channel she watches. SPEC.md
General principles: "Each agent's rule book defines 'normal'... The
rule book changes for each craft and mission type" -- so the rule book
is supplied by the caller at construction, not hardcoded here, and
every limit is a required field with no default. Callers (real
callers and tests alike) must supply real or clearly-labelled fixture
values -- same "no invented numbers" discipline as
agents/escalation_orchestrator.py's RuleSet injection.

Three senses, per SPEC.md's GRACIE / "Rate-of-change sense
(stack-wide)" / "Leash -- drift sense (stack-wide)" sections:
  - level_high / level_low: the safe-parameter crossing.
  - jump_limit: a rate (units/second) -- a step bigger than this,
    between consecutive readings, is a jump.
  - leash_window_seconds / leash_slope_limit / leash_soft_duration_
    seconds / leash_hard_duration_seconds: the leash. leash_window_
    seconds doubles as the "slack" SPEC.md describes ("a dead-band, or
    short-term averaging") -- the windowed average is itself what
    keeps normal wobble quiet, same convention already used in
    real_data_tests/opssat_ad/run_opssat_ad_test.py and
    simulated_tests/leash_drift/.

A fourth sense, added 2026-10-27 (Item 3b, SPEC.md's GRACIE
"Stillness" bullet): stuck_window_seconds / min_normal_noise -- a
sensor's variation over that window must never fall below that
minimum, or the sensor itself (not the quantity it measures) is
suspect. Required, no default, same discipline as every other limit
here -- min_normal_noise=0.0 is a legitimate, explicit way for a
caller to state "this channel's blueprint doesn't define a Stillness
limit this round" (range is never negative, so the check can never
fire), not an invented real number standing in for one.

Fault class per sense, added 2026-10-28 (Item C, SPEC.md's GRACIE
"Fault class" bullet and "Fault classes"): level/jump/leash-soft/
leash-hard/Stillness each carry their own FaultClass (MAJOR,
NON_URGENT or BOOM), required fields with no dataclass default --
every caller must pass something, but that something may honestly be
`None` ("this rule book doesn't state a class for this sense this
round"), same "required but an explicit non-claim is allowed" pattern
min_normal_noise=0.0 already uses. `None` means unknown, which SPEC.md
and GRACIE's own "Fault class" bullet both say is treated as MAJOR by
whoever looks it up (EDEN) -- GracieAgent itself never reads these
fields; she only carries them for EDEN's benefit (see agents/eden.py).

Explicitly NOT covered by a ChannelRule: jump's cross-check (did a
related channel/agent also move) and leash's context-gating (an
expected cause from another agent). Both need other agents' signals
GRACIE doesn't have yet -- out of scope until they're wired in, same
order as everything else in SPEC.md's "Wiring plan and ghost mode".
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from agents.escalation_orchestrator import FaultClass


@dataclass(frozen=True)
class ChannelRule:
    name: str
    units: str
    level_high: float
    level_low: float
    jump_limit: float  # units per second
    leash_window_seconds: float
    leash_slope_limit: float  # units per second
    leash_soft_duration_seconds: float
    leash_hard_duration_seconds: float
    stuck_window_seconds: float   # Stillness: the window to check
    min_normal_noise: float       # Stillness: variation below this is suspect
    # Fault class per sense (Item C) -- required, but None is an
    # honest "not stated" value, same pattern as min_normal_noise=0.0
    # above. EDEN (not GracieAgent) is the reader; see module docstring.
    level_fault_class: Optional[FaultClass]
    jump_fault_class: Optional[FaultClass]
    leash_soft_fault_class: Optional[FaultClass]
    leash_hard_fault_class: Optional[FaultClass]
    stillness_fault_class: Optional[FaultClass]
    # Other channels this one is linked to, per SPEC.md's Leash
    # section: a settling soft pull on a channel linked to one
    # currently in an active major fault stays with that fault's
    # handling, rather than clearing itself. Unlike the numeric
    # limits above, an empty link set is a genuine, non-arbitrary
    # default (no claimed relationship), not an invented number, so
    # this field alone may default.
    linked_channels: Tuple[str, ...] = field(default_factory=tuple)
    # Some sensors legitimately hold steady or step in some conditions
    # (e.g. a quantised channel) -- SPEC.md's Stillness bullet. Explicit
    # opt-out, defaulting to False (most sensors are NOT exempt), rather
    # than relying on an implicit min_normal_noise=0.0 (easy to mistake
    # for "not specified yet" instead of "deliberately exempt").
    allow_steady: bool = False


RuleBook = Dict[str, ChannelRule]
