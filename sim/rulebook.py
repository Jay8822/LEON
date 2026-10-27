# sim/rulebook.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Derives GRACIE's real rule book (agents/gracie_rulebook.py's
ChannelRule, one per sensor) FROM sim/blueprint.py's numbers -- "as a
real craft would be configured from its builders' data" (Jay's
clarification on Item 3). Co-designed with the blueprint, then frozen
together -- see sim/blueprint.py's module docstring; nothing here
changes after sim/COMMISSIONING.md's checkpoint commit.

No linked_channels: the blueprint's known-interference/expected-kicks
relationships are handled at scoring time via GRACIE's existing
expected_causes input (agents/gracie.py), not via ChannelRule.
linked_channels, which is specifically leash's own settling-exception
mechanism tied to another channel's FAULT latch -- a different
concept this sim doesn't use.
"""
from agents.gracie_rulebook import ChannelRule
from sim.blueprint import (
    derive_blueprint,
    LEASH_WINDOW_SECONDS, LEASH_SOFT_DURATION_SECONDS, LEASH_HARD_DURATION_SECONDS,
)


def build_rule_book(derivation_seed=None):
    """{sensor_name: ChannelRule}, derived from the blueprint. Pass
    derivation_seed only to match a non-default blueprint seed in a
    test; the real frozen rule book always uses the blueprint's own
    default (sim/blueprint.py's DERIVATION_SEED)."""
    blueprint = derive_blueprint() if derivation_seed is None else derive_blueprint(derivation_seed)
    rules = {}
    for sensor_name, entry in blueprint.items():
        rules[sensor_name] = ChannelRule(
            name=sensor_name,
            units=entry["units"],
            level_high=entry["level_high"],
            level_low=entry["level_low"],
            jump_limit=entry["jump_limit"],
            leash_window_seconds=LEASH_WINDOW_SECONDS,
            leash_slope_limit=entry["leash_slope_limit"],
            leash_soft_duration_seconds=LEASH_SOFT_DURATION_SECONDS,
            leash_hard_duration_seconds=LEASH_HARD_DURATION_SECONDS,
        )
    return rules, blueprint
