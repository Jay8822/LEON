# sim/run_sim_test_test.py
# Added 2026-11-06 -- queued item A (Ccode update.txt). Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Checks for score_faults()'s two new rules (sim/run_sim_test.py):
a catch only counts inside the fault's own window plus grace, and no
credit if the channel was already latched FAULT when the fault
started. Hand-built per_channel_log fixtures, not a full sim run --
same "small, fast, deterministic fixture" convention as
agents/gracie_test.py, not pytest.

The window-bound fixture's numbers are not arbitrary: they mirror a
real regression found in the actual 50-seed batch (bg_jobs/queue/out/
job1_sim_50seeds.json, seed_201), verified directly against that file
and a fresh re-run before writing this test, not assumed from memory.
seed_201's noisy_sensor fault is on fuel_flow, window 12667..14467.
fuel_flow latches FAULT at sample 21078 -- 6611s after that window
closed, for a reason unrelated to noisy_sensor (left as background,
see score_background_false_alarms' own "fuel_flow first_sample_index:
21078"). The old, unbounded score_faults() scanned clear to the end of
the run and wrongly credited that same sample 21078 as noisy_sensor's
own "flagged" catch (delay=8411s) -- one real FAULT sample, double-
counted under two contradictory labels. None of seed_201's 4 faults
happens to start already-latched, so that rule's test below uses a
clean synthetic fixture instead of forcing a real case that doesn't
occur in this seed.

Run from the repo root:

    python -m sim.run_sim_test_test
"""

from sim.run_sim_test import score_faults, FAULT_SCORE_GRACE_SECONDS


def _entry(sample_index, severity, active=()):
    """One per_channel_log row. `active` names which of the sense-
    active keys are True this sample; everything else is False."""
    row = {
        "sample_index": sample_index, "severity": severity,
        "level_active": False, "jump_event": False,
        "leash_soft_active": False, "leash_hard_active": False,
        "stillness_active": False,
    }
    for key in active:
        row[key] = True
    return row


def _nominal_run(length, start=0):
    return [_entry(i, "NOMINAL") for i in range(start, start + length)]


def test_catch_outside_window_plus_grace_is_not_credited():
    """seed_201-shaped regression: a genuine catch inside the fault's
    own window, PLUS an unrelated later FAULT far past end_s+grace,
    must not be credited to this fault."""
    channel = "fuel_flow"
    fault = {"name": "noisy_sensor", "channel": channel, "start_s": 12667, "end_s": 14467}
    log = _nominal_run(12667, start=0)  # 0..12666, NOMINAL
    log += [_entry(i, "FAULT", active=("level_active",)) for i in range(12667, 12700)]  # genuine catch, inside window
    log += _nominal_run(21078 - 12700, start=12700)  # back to NOMINAL until the unrelated later fault
    log += [_entry(i, "FAULT", active=("level_active",)) for i in range(21078, 21085)]  # unrelated later FAULT
    per_channel_log = {channel: log}

    [result] = score_faults(per_channel_log, [fault])
    combined = result["senses"]["combined"]
    assert combined["flagged"] is True
    assert combined["flagged_delay_seconds"] == 0, "must attribute to the genuine in-window catch, not sample 21078"
    assert result["already_latched"] is False


def test_catch_only_after_window_plus_grace_is_missed_not_credited():
    """Same shape, but with NO genuine in-window catch at all -- only
    the far-away, unrelated FAULT. Must score as missed (None), not
    silently credit the unrelated one. This is exactly what the old,
    unbounded score_faults() got wrong on seed_201's noisy_sensor."""
    channel = "fuel_flow"
    fault = {"name": "noisy_sensor", "channel": channel, "start_s": 12667, "end_s": 14467}
    log = _nominal_run(21085)  # NOMINAL throughout, including the whole fault window + grace
    for i in range(21078, 21085):
        log[i] = _entry(i, "FAULT", active=("level_active",))  # unrelated later FAULT, same sample as real seed_201
    per_channel_log = {channel: log}

    default_result, = score_faults(per_channel_log, [fault])
    assert default_result["senses"]["combined"]["flagged"] is False, \
        "the unrelated FAULT at 21078 is 6611s past end_s=14467 -- well outside end_s + grace"

    # The OLD, unbounded behaviour (grace effectively covering the whole run) DID wrongly catch it --
    # proves the two code paths actually differ, not just that the new one happens to return None.
    old_style_result, = score_faults(per_channel_log, [fault], grace_seconds=10**6)
    assert old_style_result["senses"]["combined"]["flagged"] is True
    assert old_style_result["senses"]["combined"]["flagged_delay_seconds"] == 21078 - 12667


def test_grace_zero_excludes_a_catch_just_after_end_s():
    """grace=0 means exactly start_s..end_s, nothing past it -- the
    "also report every result at grace 0" requirement."""
    channel = "attitude_rate"
    fault = {"name": "stuck_sensor", "channel": channel, "start_s": 100, "end_s": 200}
    log = _nominal_run(205)
    log[204] = _entry(204, "FAULT", active=("stillness_active",))  # 4 samples past end_s
    per_channel_log = {channel: log}

    default_result, = score_faults(per_channel_log, [fault])  # default grace comfortably covers +4s
    assert default_result["senses"]["combined"]["flagged"] is True

    zero_grace_result, = score_faults(per_channel_log, [fault], grace_seconds=0)
    assert zero_grace_result["senses"]["combined"]["flagged"] is False, \
        "grace=0 must cut off exactly at end_s; sample 204 is past it"


def test_already_latched_before_fault_start_gets_no_credit():
    """Channel is already FAULT the sample before the fault starts,
    and stays FAULT all through the fault's own window -- that's a
    pre-existing false latch continuing, not this fault being caught.
    No seed in the real 50-seed batch happens to start this way (all 4
    of seed_201's faults begin from NOMINAL -- checked directly), so
    this is a clean synthetic fixture, not a real-data replay."""
    channel = "battery_current"
    fault = {"name": "bad_engine_burn", "channel": channel, "start_s": 50, "end_s": 70}
    log = _nominal_run(49)
    log += [_entry(i, "FAULT", active=("level_active",)) for i in range(49, 90)]  # latched from 49, through and past the fault
    per_channel_log = {channel: log}

    result, = score_faults(per_channel_log, [fault])
    assert result["already_latched"] is True
    for sense, scored in result["senses"].items():
        assert scored["noticed"] is False, (sense, scored)
        assert scored["flagged"] is False, (sense, scored)


def test_already_latched_check_ignores_a_fault_starting_at_sample_zero():
    """start_s=0 has no "sample before" to check -- treated as not
    already latched (nothing to inherit a false latch from)."""
    channel = "battery_voltage"
    fault = {"name": "dying_battery", "channel": channel, "start_s": 0, "end_s": 20}
    log = [_entry(i, "FAULT", active=("level_active",)) for i in range(25)]
    per_channel_log = {channel: log}

    result, = score_faults(per_channel_log, [fault])
    assert result["already_latched"] is False
    assert result["senses"]["combined"]["flagged"] is True
    assert result["senses"]["combined"]["flagged_delay_seconds"] == 0


def test_default_grace_is_stillness_window_not_an_invented_number():
    """The chosen grace must trace to a real, already-commissioned
    number (Stillness's own window), not a new one invented here."""
    from sim.blueprint import STILLNESS_WINDOW_SECONDS
    assert FAULT_SCORE_GRACE_SECONDS == STILLNESS_WINDOW_SECONDS


def main():
    tests = [
        test_catch_outside_window_plus_grace_is_not_credited,
        test_catch_only_after_window_plus_grace_is_missed_not_credited,
        test_grace_zero_excludes_a_catch_just_after_end_s,
        test_already_latched_before_fault_start_gets_no_credit,
        test_already_latched_check_ignores_a_fault_starting_at_sample_zero,
        test_default_grace_is_stillness_window_not_an_invented_number,
    ]
    for test in tests:
        test()
    print("All sim scorer (score_faults) checks passed.")


if __name__ == "__main__":
    main()
