// include/gracie_rulebook.hpp
// AI Stack C++ Test Build — Jay Pratt + AI (Claude Sonnet 5, Anthropic). Added 2026-10-27.
//
// Per-channel rule-book core of GRACIE, ported from agents/gracie.py
// (the any-sensor rewrite) and agents/gracie_rulebook.py. Scope, agreed
// with Jay before building (see Ccode update.txt, "NEW TASK 1b"):
//
// IN SCOPE: the per-channel rule book; level (with the "new crossing
// while already latched" distinct event, the one-way ratchet to
// FAULT); jump (incremental rate-of-change, momentary, never latches);
// leash (ring-buffer windowed slope, soft/hard duration state machine,
// including settling back to NOMINAL unless the channel is part of an
// active major fault via its own FAULT or a linked channel's); per-
// channel latching and clear_fault(channel, reset_leash_timer).
//
// OUT OF SCOPE (confirmed by Jay, not built here): the `expected`
// parameter on level (GRACIE's expected_causes input); the Diagnostic
// checklist; CHESTER's side -- no EventBus, no chester/watch
// announcements, no on_command, no aggregate multi-channel health_state
// roll-up. Every real-data test harness in this repo drives GracieAgent
// with exactly one channel in its rule book at a time (confirmed by
// reading real_data_tests/esa_adb/run_esa_adb_test.py,
// real_data_tests/esa_adb/check_pretrip.py,
// real_data_tests/opssat_ad/run_opssat_ad_test.py, and
// simulated_tests/leash_drift/run_leash_drift_test.py), so the
// aggregate roll-up is never exercised by any proof dataset either way.
//
// This module is a standalone library + test/proof executables only --
// not wired into leon_sim's cyclic executive this round (nothing
// downstream -- EDEN, CHESTER -- is ready to consume per-channel
// output yet).
#ifndef LEON_GRACIE_RULEBOOK_HPP
#define LEON_GRACIE_RULEBOOK_HPP

#include "leon_types.hpp"
#include "leon_config.hpp"

namespace leon {

// Matches agents/gracie.py's _SEVERITY_RANK vocabulary and ordering
// (NOMINAL < WARNING < FAULT) -- comparisons use the integer value.
enum class Severity : std::uint8_t {
    kNominal = 0,
    kWarning = 1,
    kFault = 2,
};

// Mirrors agents/gracie_rulebook.py's ChannelRule dataclass. Every
// numeric field is required (no invented numbers) -- the caller
// (real callers and tests alike) supplies real or clearly-labelled
// fixture values, same discipline as the Python side.
struct ChannelRule {
    FixedString name;
    FixedString units;
    double level_high;
    double level_low;
    double jump_limit;                    // units per second
    double leash_window_seconds;
    double leash_slope_limit;              // units per second
    double leash_soft_duration_seconds;
    double leash_hard_duration_seconds;
    // Other channels this one is linked to (by name, resolved by
    // lookup at check-time, not by index -- so registration order
    // never matters). An empty set is a genuine default (no claimed
    // relationship), same as the Python side's field(default_factory=tuple).
    FixedString linked_channel_names[kMaxLinkedChannels];
    int linked_channel_count;
};

// One ring-buffer entry for leash's windowed slope.
struct LeashRingEntry {
    double timestamp;
    double value;
};

// Mirrors agents/gracie.py's _ChannelState dataclass, field for field,
// except window (Python's unbounded deque) becomes a fixed-size ring
// buffer (see kLeashRingCapacity's docstring in leon_config.hpp).
struct ChannelState {
    ChannelRule rule;
    Severity latched_severity;   // level + leash latch; clear_fault resets it

    bool has_last_sample;        // for jump
    double last_sample_timestamp;
    double last_sample_value;

    LeashRingEntry ring[kLeashRingCapacity];  // for leash's windowed slope
    int ring_head;                            // index of the oldest valid entry
    int ring_count;                            // number of valid entries, 0..kLeashRingCapacity

    bool has_pull_run_start;     // leash's "how long has this pull lasted" clock
    double pull_run_start;

    // Edge-detectors for the CURRENT pull specifically, same reasoning
    // as the Python side's comment: kept separate from latched_severity
    // since that's a one-way ratchet, but a later, independent pull
    // reaching soft/hard again still needs its own edge to trigger on.
    bool soft_active;
    bool hard_active;

    // Edge-detector for LEVEL specifically -- lets a new, separate
    // crossing be logged in its own right even while latched_severity
    // is still FAULT from an earlier crossing.
    bool level_crossing_active;
};

// ~2.1MB (kLeashRingCapacity x kMaxChannels doubles-pairs, plus the
// rest of ChannelState) -- far too large for a default thread stack
// (~1MB on Windows; found the hard way, as a stack-overflow crash, in
// this module's own first test run). ALWAYS give this `static` or
// global storage duration, never a plain stack local.
struct GracieRulebookState {
    ChannelState channels[kMaxChannels];
    int channel_count;
};

// Everything process_reading needs the caller to know about this
// cycle, for this one channel -- no EventBus, no announcements (out
// of scope, see file header).
struct ProcessResult {
    Severity severity;                    // latched_severity after this reading
    bool jump_event;                       // this cycle's reading triggered a jump
    bool leash_settled;                    // a soft-only pull settled back to NOMINAL this cycle
    bool new_crossing_while_latched;       // a fresh level crossing started while already latched FAULT
    bool has_slope;                        // whether the leash window was full enough to produce a slope
    double slope;                          // the windowed slope, only meaningful if has_slope
};

Status gracie_rulebook_init(GracieRulebookState* state);

// Registers a new channel; *out_index is stable for the state's
// lifetime (Rule 3: no reallocation, so a returned index never
// moves). Fails with kInvalidArgument once kMaxChannels are registered.
Status gracie_rulebook_add_channel(GracieRulebookState* state,
                                    const char* channel_name,
                                    const ChannelRule* rule,
                                    int* out_index);

// Linear scan over a fixed, small (<=kMaxChannels) array -- Rule 2's
// fixed bound, no map/hash needed at this scale. Returns
// kInvalidArgument (not found) rather than a special "not found" enum
// value, matching this codebase's existing two-value Status pattern.
Status gracie_rulebook_find_channel(const GracieRulebookState* state,
                                     const char* channel_name,
                                     int* out_index);

// Processes one reading for one already-registered channel. Order
// matches agents/gracie.py's process_readings exactly: level, then
// jump, then leash -- leash's "part of an active major fault" check
// reads latched_severity AFTER level has already run this same cycle,
// so the order is load-bearing, not incidental.
Status gracie_rulebook_process_reading(GracieRulebookState* state,
                                        int channel_index,
                                        double timestamp,
                                        double value,
                                        ProcessResult* out_result);

// Mirrors agents/gracie.py's clear_fault(channel, reset_leash_timer).
// Does NOT touch the leash ring buffer or level_crossing_active --
// same as the Python side, which only ever resets latched_severity
// and (if reset_leash_timer) pull_run_start/soft_active/hard_active.
Status gracie_rulebook_clear_fault(GracieRulebookState* state,
                                    int channel_index,
                                    bool reset_leash_timer);

// Mirrors clear_fault(channel=None) -- clears every registered channel.
Status gracie_rulebook_clear_fault_all(GracieRulebookState* state,
                                        bool reset_leash_timer);

}  // namespace leon

#endif  // LEON_GRACIE_RULEBOOK_HPP
