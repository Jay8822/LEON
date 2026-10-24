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

Explicitly NOT covered by a ChannelRule: jump's cross-check (did a
related channel/agent also move) and leash's context-gating (an
expected cause from another agent). Both need other agents' signals
GRACIE doesn't have yet -- out of scope until they're wired in, same
order as everything else in SPEC.md's "Wiring plan and ghost mode".
"""

from dataclasses import dataclass, field
from typing import Dict, Tuple


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
    # Other channels this one is linked to, per SPEC.md's Leash
    # section: a settling soft pull on a channel linked to one
    # currently in an active major fault stays with that fault's
    # handling, rather than clearing itself. Unlike the numeric
    # limits above, an empty link set is a genuine, non-arbitrary
    # default (no claimed relationship), not an invented number, so
    # this field alone may default.
    linked_channels: Tuple[str, ...] = field(default_factory=tuple)


RuleBook = Dict[str, ChannelRule]
