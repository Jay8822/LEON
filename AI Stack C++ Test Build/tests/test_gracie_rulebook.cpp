// tests/test_gracie_rulebook.cpp
// AI Stack C++ Test Build — Jay Pratt + AI (Claude Sonnet 5, Anthropic). Added 2026-10-27.
// Mirrors agents/gracie_test.py's cases, adapted to this module's
// scope: no EventBus/chester announcements, no aggregate multi-channel
// health_state roll-up, no expected_causes (see gracie_rulebook.hpp's
// file header for the exact scope boundary) -- so each check here
// looks at ProcessResult / per-channel severity directly instead.
//
// Same fixture rule books as agents/gracie_test.py, carried over
// verbatim where the numbers matter for the test (arbitrary, round
// numbers chosen for easy arithmetic -- never claimed as real
// thresholds, same discipline as the Python fixture).
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdlib>

#include "gracie_rulebook.hpp"

namespace {

using leon::CausingSense;
using leon::ChannelRule;
using leon::FaultClass;
using leon::GracieRulebookState;
using leon::ProcessResult;
using leon::Severity;
using leon::Status;

void fail(const char* label) {
    std::fprintf(stderr, "FAIL: %s\n", label);
    std::exit(1);
}

void check(bool condition, const char* label) {
    if (!condition) {
        fail(label);
    }
}

ChannelRule make_rule(double level_high, double level_low, double jump_limit,
                      double leash_window_seconds, double leash_slope_limit,
                      double leash_soft_duration_seconds, double leash_hard_duration_seconds) {
    ChannelRule rule{};
    rule.level_high = level_high;
    rule.level_low = level_low;
    rule.jump_limit = jump_limit;
    rule.leash_window_seconds = leash_window_seconds;
    rule.leash_slope_limit = leash_slope_limit;
    rule.leash_soft_duration_seconds = leash_soft_duration_seconds;
    rule.leash_hard_duration_seconds = leash_hard_duration_seconds;
    rule.linked_channel_count = 0;
    return rule;
}

int add_channel(GracieRulebookState* state, const char* name, const ChannelRule& rule) {
    int index = -1;
    check(leon::gracie_rulebook_add_channel(state, name, &rule, &index) == Status::kOk, "add_channel");
    return index;
}

ProcessResult process(GracieRulebookState* state, int channel_index, double timestamp, double value) {
    ProcessResult result{};
    check(leon::gracie_rulebook_process_reading(state, channel_index, timestamp, value, &result)
              == Status::kOk,
          "process_reading");
    return result;
}

// --- test cases -------------------------------------------------------

void test_level_is_independent_per_channel() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    const ChannelRule temp_rule = make_rule(55.0, -20.0, 5.0, 10.0, 1.0, 20.0, 40.0);
    const ChannelRule rad_rule = make_rule(40.0, 0.0, 3.0, 10.0, 0.5, 20.0, 40.0);
    const int temp_c = add_channel(&state, "temp_c", temp_rule);
    const int radiation = add_channel(&state, "radiation", rad_rule);

    check(process(&state, temp_c, 0.0, 30.0).severity == Severity::kNominal, "temp nominal");
    check(process(&state, radiation, 0.0, 10.0).severity == Severity::kNominal, "rad nominal");

    // Only temp_c crosses -- radiation must not be dragged along with it.
    check(process(&state, temp_c, 1.0, 56.0).severity == Severity::kFault, "temp crosses -> FAULT");
    check(process(&state, radiation, 1.0, 10.0).severity == Severity::kNominal,
          "radiation unaffected by temp_c's crossing");

    // Now radiation crosses too, independently.
    check(process(&state, temp_c, 2.0, 30.0).severity == Severity::kFault, "temp still latched");
    check(process(&state, radiation, 2.0, 45.0).severity == Severity::kFault, "radiation now FAULT too");
    std::printf("  ok: level crossings are independent per channel, no AND condition\n");
}

void test_clear_fault_per_channel_and_all() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    const ChannelRule temp_rule = make_rule(55.0, -20.0, 5.0, 10.0, 1.0, 20.0, 40.0);
    const ChannelRule rad_rule = make_rule(40.0, 0.0, 3.0, 10.0, 0.5, 20.0, 40.0);
    const int temp_c = add_channel(&state, "temp_c", temp_rule);
    const int radiation = add_channel(&state, "radiation", rad_rule);

    check(process(&state, temp_c, 0.0, 56.0).severity == Severity::kFault, "temp FAULT");
    check(process(&state, radiation, 0.0, 45.0).severity == Severity::kFault, "radiation FAULT");

    check(leon::gracie_rulebook_clear_fault(&state, temp_c, true) == Status::kOk, "clear temp_c");
    check(state.channels[temp_c].latched_severity == Severity::kNominal, "temp_c cleared");
    check(state.channels[radiation].latched_severity == Severity::kFault, "radiation still latched");

    check(leon::gracie_rulebook_clear_fault_all(&state, true) == Status::kOk, "clear all");
    check(state.channels[temp_c].latched_severity == Severity::kNominal, "temp_c still nominal");
    check(state.channels[radiation].latched_severity == Severity::kNominal, "radiation now nominal");
    std::printf("  ok: clear_fault(channel) clears just that channel; clear_fault_all clears every channel\n");
}

void test_jump_is_momentary_not_latched() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    const ChannelRule rad_rule = make_rule(40.0, 0.0, 3.0, 10.0, 0.5, 20.0, 40.0);
    const int radiation = add_channel(&state, "radiation", rad_rule);

    check(process(&state, radiation, 0.0, 0.0).jump_event == false, "no jump at t=0");

    ProcessResult r1 = process(&state, radiation, 1.0, 10.0);  // rate=10/s > jump_limit=3/s
    check(r1.jump_event == true, "jump fires");

    ProcessResult r2 = process(&state, radiation, 2.0, 10.0);  // no change -- no new jump
    check(r2.jump_event == false, "no new jump without a new rate change");
    check(r2.severity == Severity::kNominal, "a jump must not latch -- it's momentary");
    std::printf("  ok: jump fires on its own cycle only, never latches\n");
}

void test_leash_soft_then_hard_by_duration() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    const ChannelRule drift_rule = make_rule(1e6, -1e6, 1000.0, 10.0, 1.0, 20.0, 40.0);
    const int drift = add_channel(&state, "drift_channel", drift_rule);

    // A steady ramp of 2 units/s -- comfortably over leash_slope_limit
    // (1.0/s). window=10s, soft=20s, hard=40s. The pull begins once
    // the window first fills (t=10), so soft is expected at t=30
    // (10+20), hard at t=50 (10+40).
    for (int t = 0; t <= 50; ++t) {
        const Severity severity = process(&state, drift, static_cast<double>(t), 2.0 * t).severity;
        if (t < 30) {
            check(severity == Severity::kNominal, "before soft");
        } else if (t < 50) {
            check(severity == Severity::kWarning, "between soft and hard");
        } else {
            check(severity == Severity::kFault, "at/after hard");
        }
    }
    std::printf("  ok: leash reaches soft at its soft duration, hard at its (longer) hard duration\n");
}

void test_clear_fault_default_resets_the_leash_timer() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    const ChannelRule drift_rule = make_rule(1e6, -1e6, 1000.0, 10.0, 1.0, 20.0, 40.0);
    const int drift = add_channel(&state, "drift_channel", drift_rule);

    for (int t = 0; t <= 30; ++t) {
        process(&state, drift, static_cast<double>(t), 2.0 * t);
    }
    check(state.channels[drift].latched_severity == Severity::kWarning, "WARNING at t=30");

    check(leon::gracie_rulebook_clear_fault(&state, drift, true) == Status::kOk, "clear_fault default");
    check(state.channels[drift].latched_severity == Severity::kNominal, "cleared to NOMINAL");

    // The pull never stopped (still ramping), but the clock restarted
    // fresh at t=31 -- hard (31+40) is now expected at t=71, NOT
    // anywhere near the original t=50.
    for (int t = 31; t < 50; ++t) {
        process(&state, drift, static_cast<double>(t), 2.0 * t);
    }
    check(state.channels[drift].latched_severity == Severity::kNominal,
          "the default clear_fault resets the clock, so nothing should have re-fired by the old t=50");
    for (int t = 50; t <= 71; ++t) {
        process(&state, drift, static_cast<double>(t), 2.0 * t);
    }
    check(state.channels[drift].latched_severity == Severity::kFault,
          "hard should now arrive ~40s after the fresh start at t=31, i.e. at t=71");
    std::printf("  ok: clear_fault's default (reset_leash_timer=true) resets the leash clock, unchanged\n");
}

void test_clear_fault_can_leave_the_leash_timer_running() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    const ChannelRule drift_rule = make_rule(1e6, -1e6, 1000.0, 10.0, 1.0, 20.0, 40.0);
    const int drift = add_channel(&state, "drift_channel", drift_rule);

    for (int t = 0; t <= 30; ++t) {
        process(&state, drift, static_cast<double>(t), 2.0 * t);
    }
    check(state.channels[drift].latched_severity == Severity::kWarning, "WARNING at t=30");

    check(leon::gracie_rulebook_clear_fault(&state, drift, false) == Status::kOk,
          "clear_fault(reset_leash_timer=false)");
    check(state.channels[drift].latched_severity == Severity::kNominal, "latch cleared");

    // The pull keeps going, uninterrupted, at the same slope. Because
    // the clock was NOT reset, hard still arrives at the ORIGINAL
    // t=50 (10+40), not 40s after the clear.
    for (int t = 31; t < 50; ++t) {
        check(process(&state, drift, static_cast<double>(t), 2.0 * t).severity == Severity::kNominal,
              "still NOMINAL before the original t=50");
    }
    check(process(&state, drift, 50.0, 2.0 * 50).severity == Severity::kFault,
          "hard must still arrive at the original t=50 -- the clock kept running through the clear");
    std::printf("  ok: clear_fault(reset_leash_timer=false) clears the latch but leaves the leash clock running\n");
}

void test_leash_settles_back_before_hard_clears() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    const ChannelRule drift_rule = make_rule(1e6, -1e6, 1000.0, 10.0, 1.0, 20.0, 40.0);
    const int drift = add_channel(&state, "drift_channel", drift_rule);

    int t = 0;
    for (t = 0; t <= 30; ++t) {
        process(&state, drift, static_cast<double>(t), 2.0 * t);
    }
    check(state.channels[drift].latched_severity == Severity::kWarning, "WARNING at t=30");

    // Hold flat -- the windowed slope decays toward 0 well before
    // hard's duration (40s) would otherwise be reached, so the pull
    // settles back on its own.
    const double flat_value = 2.0 * t;
    bool saw_settle = false;
    for (int extra = 1; extra < 15; ++extra) {
        ProcessResult r = process(&state, drift, static_cast<double>(t + extra), flat_value);
        if (r.leash_settled) {
            saw_settle = true;
        }
    }
    check(saw_settle, "leash_settled must fire once while flat");
    check(state.channels[drift].latched_severity == Severity::kNominal,
          "a soft pull that settles back must clear itself, not stay stuck at WARNING");
    std::printf("  ok: a settling soft pull clears itself back to NOMINAL\n");
}

void test_leash_settles_back_stays_with_an_active_level_fault() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    // combo_channel: REACHABLE level bounds (unlike drift_rule's,
    // deliberately unreachable), for the "settling soft pull on a
    // channel already in an active level FAULT" case.
    const ChannelRule combo_rule = make_rule(200.0, -200.0, 1000.0, 10.0, 1.0, 20.0, 40.0);
    const int combo = add_channel(&state, "combo_channel", combo_rule);

    int t = 0;
    for (t = 0; t <= 30; ++t) {
        process(&state, combo, static_cast<double>(t), 250.0 + 2.0 * t);
    }
    check(state.channels[combo].latched_severity == Severity::kFault, "FAULT from LEVEL, not leash");

    const double flat_value = 250.0 + 2.0 * t;
    for (int extra = 1; extra < 15; ++extra) {
        process(&state, combo, static_cast<double>(t + extra), flat_value);
    }
    check(state.channels[combo].latched_severity == Severity::kFault,
          "a settling leash pull must not clear a channel that's independently still FAULT");
    std::printf("  ok: a settling soft pull stays with an already-active level FAULT, not handed off\n");
}

void test_leash_settles_back_stays_with_a_linked_channels_active_fault() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    ChannelRule linked_a_rule = make_rule(1e6, -1e6, 1000.0, 10.0, 1.0, 20.0, 40.0);
    check(leon::fixed_string_set(&linked_a_rule.linked_channel_names[0], "linked_b") == Status::kOk,
          "set linked name");
    linked_a_rule.linked_channel_count = 1;
    const ChannelRule linked_b_rule = make_rule(200.0, -200.0, 1000.0, 10.0, 1.0, 20.0, 40.0);

    const int linked_a = add_channel(&state, "linked_a", linked_a_rule);
    const int linked_b = add_channel(&state, "linked_b", linked_b_rule);

    // B gets its own level FAULT first -- A is linked to B, not the
    // other way round.
    check(process(&state, linked_b, -1.0, 300.0).severity == Severity::kFault, "B FAULT");

    int t = 0;
    for (t = 0; t <= 30; ++t) {
        process(&state, linked_a, static_cast<double>(t), 2.0 * t);
    }
    check(state.channels[linked_a].latched_severity == Severity::kWarning, "A WARNING from its own leash pull");

    const double flat_value = 2.0 * t;
    for (int extra = 1; extra < 15; ++extra) {
        process(&state, linked_a, static_cast<double>(t + extra), flat_value);
    }
    check(state.channels[linked_a].latched_severity == Severity::kWarning,
          "A must stay latched while B, which A is linked to, is still an active major fault");
    std::printf("  ok: a settling soft pull stays latched when linked to a DIFFERENT channel's active fault\n");
}

void test_new_crossing_while_latched_logs_but_does_not_change_anything() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    const ChannelRule temp_rule = make_rule(55.0, -20.0, 5.0, 10.0, 1.0, 20.0, 40.0);
    const int temp_c = add_channel(&state, "temp_c", temp_rule);

    // Small steps (well under jump_limit=5.0/s) so jump noise doesn't
    // confound what's being tested here.
    ProcessResult r0 = process(&state, temp_c, 0.0, 56.0);  // first crossing -> FAULT
    check(r0.severity == Severity::kFault, "first crossing -> FAULT");
    check(r0.new_crossing_while_latched == false, "the FIRST crossing is not 'while already latched'");
    check(state.channels[temp_c].level_crossing_active == true, "crossing active");

    ProcessResult r1 = process(&state, temp_c, 1.0, 52.0);  // back in bounds (delta=4)
    check(r1.severity == Severity::kFault, "still latched -- only clear_fault undoes it");
    check(state.channels[temp_c].level_crossing_active == false, "crossing cleared");

    // A second, separate crossing while still latched FAULT from the
    // first -- severity is unaffected (already FAULT, stays FAULT),
    // but the edge-detector proves this is treated as a fresh
    // crossing, not silently folded into the first.
    ProcessResult r2 = process(&state, temp_c, 2.0, 56.0);  // delta=4
    check(r2.severity == Severity::kFault, "still FAULT");
    check(r2.new_crossing_while_latched == true, "a fresh crossing while already latched is flagged");
    check(state.channels[temp_c].level_crossing_active == true, "crossing active again");
    std::printf("  ok: a new crossing while already latched FAULT logs a fresh event, latch stays unchanged\n");
}

void test_find_channel_reports_unrecognized_name() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    const ChannelRule temp_rule = make_rule(55.0, -20.0, 5.0, 10.0, 1.0, 20.0, 40.0);
    add_channel(&state, "temp_c", temp_rule);

    int index = -1;
    check(leon::gracie_rulebook_find_channel(&state, "mystery_channel", &index) == Status::kInvalidArgument,
          "an unrecognized channel name is reported as not found, not guessed at");
    std::printf("  ok: a channel with no rule-book entry is reported as not found\n");
}

void test_clock_fault_on_backward_timestamp() {
    // Ccode update.txt, 2026-11-05, "CLOCK-FAULT PLAN": a reading
    // timestamped earlier than the channel's last one is flagged
    // FAULT, and leash's ring / jump's last sample reset and reseed
    // from that reading -- not left stale.
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    ChannelRule rad_rule = make_rule(40.0, 0.0, 3.0, 10.0, 0.5, 20.0, 40.0);
    rad_rule.clock_fault_repeat_count = 3;
    rad_rule.clock_fault_repeat_window_seconds = 60.0;
    const int radiation = add_channel(&state, "radiation", rad_rule);

    check(process(&state, radiation, 10.0, 5.0).severity == Severity::kNominal, "t=10 nominal");
    check(process(&state, radiation, 20.0, 5.0).severity == Severity::kNominal, "t=20 nominal");

    const ProcessResult r = process(&state, radiation, 15.0, 5.0);  // backward: 15 < 20
    check(r.clock_event == true, "clock_event fires");
    check(r.clock_repeated == false, "only 1 occurrence so far, N=3");
    check(r.severity == Severity::kFault, "a backward timestamp is flagged FAULT");
    const leon::ChannelState& cs = state.channels[radiation];
    check(cs.ring_count == 1, "leash ring must reset, not keep the pre-jump entries");
    check(cs.has_last_sample == true && cs.last_sample_timestamp == 15.0,
          "jump's last sample must reseed from this reading");
    std::printf("  ok: a single backward timestamp is flagged FAULT, leash/jump state reset\n");
}

void test_clock_fault_escalates_to_repeated_within_window() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    ChannelRule rad_rule = make_rule(40.0, 0.0, 3.0, 10.0, 0.5, 20.0, 40.0);
    rad_rule.clock_fault_repeat_count = 3;
    rad_rule.clock_fault_repeat_window_seconds = 60.0;
    const int radiation = add_channel(&state, "radiation", rad_rule);

    process(&state, radiation, 100.0, 5.0);
    check(process(&state, radiation, 90.0, 5.0).clock_repeated == false, "jump 1, ref=100");
    process(&state, radiation, 95.0, 5.0);
    check(process(&state, radiation, 85.0, 5.0).clock_repeated == false, "jump 2, ref=95 (within 60s of 100)");
    process(&state, radiation, 90.0, 5.0);
    check(process(&state, radiation, 80.0, 5.0).clock_repeated == true,
          "jump 3, ref=90 (within 60s of 100) -- 3rd occurrence must escalate");
    std::printf("  ok: N occurrences within T seconds escalate to clock_repeated\n");
}

void test_clock_fault_does_not_escalate_outside_the_window() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    ChannelRule rad_rule = make_rule(40.0, 0.0, 3.0, 10.0, 0.5, 20.0, 40.0);
    rad_rule.clock_fault_repeat_count = 3;
    rad_rule.clock_fault_repeat_window_seconds = 60.0;
    const int radiation = add_channel(&state, "radiation", rad_rule);

    process(&state, radiation, 1000.0, 5.0);
    check(process(&state, radiation, 990.0, 5.0).clock_repeated == false, "jump 1, ref=1000");
    process(&state, radiation, 995.0, 5.0);
    check(process(&state, radiation, 985.0, 5.0).clock_repeated == false, "jump 2, ref=995 (within 60s of 1000)");
    process(&state, radiation, 2000.0, 5.0);
    check(process(&state, radiation, 1990.0, 5.0).clock_repeated == false,
          "jump 3, ref=2000 -- far outside 60s of jumps 1/2, which must have aged out");
    std::printf("  ok: occurrences older than T seconds don't count toward the N-in-T escalation\n");
}

void test_clear_fault_resets_the_clock_fault_occurrence_count() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    ChannelRule rad_rule = make_rule(40.0, 0.0, 3.0, 10.0, 0.5, 20.0, 40.0);
    rad_rule.clock_fault_repeat_count = 3;
    rad_rule.clock_fault_repeat_window_seconds = 60.0;
    const int radiation = add_channel(&state, "radiation", rad_rule);

    process(&state, radiation, 100.0, 5.0);
    process(&state, radiation, 90.0, 5.0);
    process(&state, radiation, 95.0, 5.0);
    process(&state, radiation, 85.0, 5.0);
    check(state.channels[radiation].clock_fault_count == 2, "2 occurrences recorded");

    check(leon::gracie_rulebook_clear_fault(&state, radiation, true) == Status::kOk, "clear_fault");
    check(state.channels[radiation].clock_fault_count == 0, "clear_fault resets the occurrence count");

    process(&state, radiation, 200.0, 5.0);
    check(process(&state, radiation, 190.0, 5.0).clock_repeated == false,
          "1st occurrence since sign-off must not immediately re-escalate");
    std::printf("  ok: clear_fault resets the clock-fault occurrence count, not just the latch\n");
}

void test_stillness_flags_a_sensor_that_never_varies_enough() {
    // Mirrors agents/gracie_test.py's STUCK_RULE: stuck_window_seconds=5.0,
    // min_normal_noise=2.0. Level/jump/leash are all set unreachable on
    // this channel, so only Stillness can produce a FAULT here.
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    ChannelRule stuck_rule = make_rule(1e6, -1e6, 1e6, 10.0, 1e6, 1e6, 1e6);
    stuck_rule.stuck_window_seconds = 5.0;
    stuck_rule.min_normal_noise = 2.0;
    const int stuck = add_channel(&state, "stuck_channel", stuck_rule);

    const double readings[] = {10.0, 10.5, 11.0, 10.8, 10.3, 10.6};  // range 1.0, under the 2.0 minimum
    ProcessResult r{};
    for (int t = 0; t < 6; ++t) {
        r = process(&state, stuck, static_cast<double>(t), readings[t]);
        if (t < 5) {
            check(r.sensor_health_fault == false, "window doesn't cover the full 5.0s yet -- no verdict possible");
        }
    }
    check(r.severity == Severity::kFault, "Stillness FAULT");
    check(r.sensor_health_fault == true,
          "a Stillness fault must be tagged distinctly from an ordinary level/leash fault");
    std::printf("  ok: a sensor whose variation stays below the blueprint's minimum is flagged, tagged sensor-health\n");
}

void test_stillness_does_not_fire_on_a_sensor_that_varies_enough() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    ChannelRule stuck_rule = make_rule(1e6, -1e6, 1e6, 10.0, 1e6, 1e6, 1e6);
    stuck_rule.stuck_window_seconds = 5.0;
    stuck_rule.min_normal_noise = 2.0;
    const int stuck = add_channel(&state, "stuck_channel", stuck_rule);

    const double readings[] = {0.0, 5.0, 10.0, 3.0, 8.0, 1.0};  // range 10.0, well over the 2.0 minimum
    ProcessResult r{};
    for (int t = 0; t < 6; ++t) {
        r = process(&state, stuck, static_cast<double>(t), readings[t]);
    }
    check(r.severity == Severity::kNominal, "no fault");
    check(r.sensor_health_fault == false, "a sensor with real variation never trips Stillness");
    std::printf("  ok: a sensor with real variation never trips Stillness\n");
}

void test_allow_steady_exempts_a_channel_from_stillness() {
    // STEADY_RULE has the SAME stuck_window_seconds/min_normal_noise as
    // the stuck-channel tests above, but allow_steady=true.
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    ChannelRule steady_rule = make_rule(1e6, -1e6, 1e6, 10.0, 1e6, 1e6, 1e6);
    steady_rule.stuck_window_seconds = 5.0;
    steady_rule.min_normal_noise = 2.0;
    steady_rule.allow_steady = true;
    const int steady = add_channel(&state, "steady_channel", steady_rule);

    const double readings[] = {10.0, 10.5, 11.0, 10.8, 10.3, 10.6};  // identical pattern to the stuck-channel test
    ProcessResult r{};
    for (int t = 0; t < 6; ++t) {
        r = process(&state, steady, static_cast<double>(t), readings[t]);
    }
    check(r.severity == Severity::kNominal, "no fault");
    check(r.sensor_health_fault == false, "allow_steady exempts a channel from Stillness entirely");
    std::printf("  ok: allow_steady exempts a channel from Stillness entirely\n");
}

void test_stillness_latch_is_released_by_clear_fault() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    ChannelRule stuck_rule = make_rule(1e6, -1e6, 1e6, 10.0, 1e6, 1e6, 1e6);
    stuck_rule.stuck_window_seconds = 5.0;
    stuck_rule.min_normal_noise = 2.0;
    const int stuck = add_channel(&state, "stuck_channel", stuck_rule);

    const double readings[] = {10.0, 10.5, 11.0, 10.8, 10.3, 10.6};
    for (int t = 0; t < 6; ++t) {
        process(&state, stuck, static_cast<double>(t), readings[t]);
    }
    check(state.channels[stuck].latched_severity == Severity::kFault, "FAULT");
    check(state.channels[stuck].stillness_active == true, "sensor-health flagged");

    check(leon::gracie_rulebook_clear_fault(&state, stuck, true) == Status::kOk, "clear_fault");
    check(state.channels[stuck].latched_severity == Severity::kNominal, "cleared");
    check(state.channels[stuck].stillness_active == false, "clear_fault releases a Stillness latch, same as any other");
    std::printf("  ok: clear_fault releases a Stillness latch, same as any other\n");
}

void test_causing_sense_is_level() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    const ChannelRule temp_rule = make_rule(55.0, -20.0, 1000.0, 10.0, 1.0, 20.0, 40.0);
    const int temp_c = add_channel(&state, "temp_c", temp_rule);

    check(process(&state, temp_c, 0.0, 30.0).causing_sense == CausingSense::kNone, "nominal, no cause yet");
    check(process(&state, temp_c, 1.0, 56.0).causing_sense == CausingSense::kLevel, "level crossing");

    // Drops back in bounds -- the ratchet stays, and so must its cause.
    const ProcessResult r = process(&state, temp_c, 2.0, 30.0);
    check(r.severity == Severity::kFault, "still FAULT");
    check(r.causing_sense == CausingSense::kLevel, "cause persists through the ratchet");

    check(leon::gracie_rulebook_clear_fault(&state, temp_c, true) == Status::kOk, "clear_fault");
    check(state.channels[temp_c].causing_sense == CausingSense::kNone, "cause cleared");
    std::printf("  ok: causing_sense is kLevel for a level crossing, persists until clear_fault\n");
}

void test_causing_sense_is_leash_soft_then_leash_hard() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    const ChannelRule drift_rule = make_rule(1e6, -1e6, 1000.0, 10.0, 1.0, 20.0, 40.0);
    const int drift = add_channel(&state, "drift_channel", drift_rule);

    for (int t = 0; t <= 50; ++t) {
        const CausingSense cause = process(&state, drift, static_cast<double>(t), 2.0 * t).causing_sense;
        if (t < 30) {
            check(cause == CausingSense::kNone, "before soft");
        } else if (t < 50) {
            check(cause == CausingSense::kLeashSoft, "between soft and hard");
        } else {
            check(cause == CausingSense::kLeashHard, "at/after hard");
        }
    }
    std::printf("  ok: causing_sense tracks leash_soft, then switches to leash_hard once hard fires\n");
}

void test_causing_sense_is_stillness() {
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    ChannelRule stuck_rule = make_rule(1e6, -1e6, 1e6, 10.0, 1e6, 1e6, 1e6);
    stuck_rule.stuck_window_seconds = 5.0;
    stuck_rule.min_normal_noise = 2.0;
    const int stuck = add_channel(&state, "stuck_channel", stuck_rule);

    const double readings[] = {10.0, 10.5, 11.0, 10.8, 10.3, 10.6};  // range 1.0, under the 2.0 minimum
    ProcessResult r{};
    for (int t = 0; t < 6; ++t) {
        r = process(&state, stuck, static_cast<double>(t), readings[t]);
    }
    check(r.causing_sense == CausingSense::kStillness, "causing_sense is kStillness for a Stillness fault");
    std::printf("  ok: causing_sense is kStillness for a Stillness fault\n");
}

void test_fault_class_fields_round_trip_through_the_rule_book() {
    // GracieRulebookState never reads these itself (EDEN's vocabulary,
    // not GRACIE's -- see gracie_rulebook.hpp's file header); this only
    // confirms the fields are stored and retrievable, and that a
    // zero-initialized rule defaults every one to kNotStated, matching
    // Python's None-by-default/"no invented numbers" discipline.
    static GracieRulebookState state{};
    check(leon::gracie_rulebook_init(&state) == Status::kOk, "init");
    ChannelRule rule = make_rule(55.0, -20.0, 1000.0, 10.0, 1.0, 20.0, 40.0);
    check(rule.level_fault_class == FaultClass::kNotStated, "zero-init defaults to kNotStated");
    rule.level_fault_class = FaultClass::kMajor;
    rule.jump_fault_class = FaultClass::kNonUrgent;
    rule.leash_soft_fault_class = FaultClass::kNonUrgent;
    rule.leash_hard_fault_class = FaultClass::kMajor;
    rule.stillness_fault_class = FaultClass::kBoom;
    rule.clock_fault_class = FaultClass::kNonUrgent;
    rule.clock_repeated_fault_class = FaultClass::kMajor;
    const int ch = add_channel(&state, "temp_c", rule);

    const ChannelRule& stored = state.channels[ch].rule;
    check(stored.level_fault_class == FaultClass::kMajor, "level");
    check(stored.jump_fault_class == FaultClass::kNonUrgent, "jump");
    check(stored.leash_soft_fault_class == FaultClass::kNonUrgent, "leash_soft");
    check(stored.leash_hard_fault_class == FaultClass::kMajor, "leash_hard");
    check(stored.stillness_fault_class == FaultClass::kBoom, "stillness");
    check(stored.clock_fault_class == FaultClass::kNonUrgent, "clock");
    check(stored.clock_repeated_fault_class == FaultClass::kMajor, "clock_repeated");
    std::printf("  ok: per-sense fault classes round-trip through the rule book, kNotStated by default\n");
}

}  // namespace

int main() {
    test_level_is_independent_per_channel();
    test_clear_fault_per_channel_and_all();
    test_jump_is_momentary_not_latched();
    test_leash_soft_then_hard_by_duration();
    test_clear_fault_default_resets_the_leash_timer();
    test_clear_fault_can_leave_the_leash_timer_running();
    test_leash_settles_back_before_hard_clears();
    test_leash_settles_back_stays_with_an_active_level_fault();
    test_leash_settles_back_stays_with_a_linked_channels_active_fault();
    test_new_crossing_while_latched_logs_but_does_not_change_anything();
    test_find_channel_reports_unrecognized_name();
    test_clock_fault_on_backward_timestamp();
    test_clock_fault_escalates_to_repeated_within_window();
    test_clock_fault_does_not_escalate_outside_the_window();
    test_clear_fault_resets_the_clock_fault_occurrence_count();
    test_stillness_flags_a_sensor_that_never_varies_enough();
    test_stillness_does_not_fire_on_a_sensor_that_varies_enough();
    test_allow_steady_exempts_a_channel_from_stillness();
    test_stillness_latch_is_released_by_clear_fault();
    test_causing_sense_is_level();
    test_causing_sense_is_leash_soft_then_leash_hard();
    test_causing_sense_is_stillness();
    test_fault_class_fields_round_trip_through_the_rule_book();
    std::printf("All GRACIE rule-book core checks passed.\n");
    return 0;
}
