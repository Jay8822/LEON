# real_data_tests/cpp_proof/export_opssat_fragment.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Proof dataset 2 of 3 for NEW TASK 1b: one real OPS-SAT test
fragment, with its channel's already-derived STRICT rule-book values
(same derive_thresholds/derive_jump_limits/derive_leash_limits this
folder's own run_opssat_ad_test.py uses -- reused directly, not
reimplemented). Segment 1329 (CADC0873, nominal, 38 samples, 185s) --
small and fast, but leash-evaluable (>= window + hard duration), so
this proof exercises level, jump AND leash, not just level/jump.
Segments are independent fragments (no state carries between them,
per that module's own docstring), so no clear_fault mid-run either.

Run from the repo root, after download_opssat_ad.py:

    python -m real_data_tests.cpp_proof.export_opssat_fragment
"""
import os

from agents.gracie_rulebook import ChannelRule
from real_data_tests.opssat_ad.run_opssat_ad_test import (
    load_fragments, derive_thresholds, derive_jump_limits, derive_leash_limits,
    LEASH_WINDOW_SECONDS, LEASH_SOFT_DURATION_SECONDS, LEASH_HARD_DURATION_SECONDS,
    LEASH_SLOPE_PCT,
)
from real_data_tests.cpp_proof.proof_common import (
    OUT_DIR, write_sidecar, write_readings_csv, write_reference_csv, run_reference,
)

SEGMENT_ID = "1329"
SETTING = (95, 5)  # STRICT


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    fragments = load_fragments()
    train = [f for f in fragments if f.is_train]
    frag = next(f for f in fragments if f.segment_id == SEGMENT_ID)
    channel = frag.channel

    thresholds = derive_thresholds(train, *SETTING)[channel]
    jump_limits = derive_jump_limits(train, SETTING[0])[channel]
    leash_limits = derive_leash_limits(train, LEASH_SLOPE_PCT)[channel]

    rule = ChannelRule(
        name=channel, units="u",
        level_high=thresholds["high"], level_low=thresholds["low"],
        jump_limit=jump_limits["limit"],
        leash_window_seconds=LEASH_WINDOW_SECONDS,
        leash_slope_limit=leash_limits["limit"],
        leash_soft_duration_seconds=LEASH_SOFT_DURATION_SECONDS,
        leash_hard_duration_seconds=LEASH_HARD_DURATION_SECONDS,
        stuck_window_seconds=LEASH_WINDOW_SECONDS, min_normal_noise=0.0,  # Stillness: not in the C++ port yet, not exercised here
        level_fault_class=None, jump_fault_class=None, leash_soft_fault_class=None,
        leash_hard_fault_class=None, stillness_fault_class=None,  # Item C: not stated this round
    )

    rows = [(i, t.timestamp(), v, False) for i, (t, v) in enumerate(zip(frag.timestamps, frag.values))]
    tag = f"opssat_{channel}_seg{SEGMENT_ID}"
    write_sidecar(os.path.join(OUT_DIR, f"{tag}_rule.txt"), rule)
    write_readings_csv(os.path.join(OUT_DIR, f"{tag}_readings.csv"), rows)
    log = run_reference(channel, rule, rows)
    write_reference_csv(os.path.join(OUT_DIR, f"{tag}_reference.csv"), log)

    with open(os.path.join(OUT_DIR, "opssat_manifest.txt"), "w") as f:
        f.write(tag + "\n")
    print(f"{tag}: {len(rows)} rows exported "
          f"(level=[{rule.level_low:.6g}, {rule.level_high:.6g}], jump_limit={rule.jump_limit:.6g}/s, "
          f"leash_slope_limit={rule.leash_slope_limit:.6g}/s)")


if __name__ == "__main__":
    main()
