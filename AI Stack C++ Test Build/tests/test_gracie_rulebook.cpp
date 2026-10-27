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

using leon::ChannelRule;
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
    std::printf("All GRACIE rule-book core checks passed.\n");
    return 0;
}
