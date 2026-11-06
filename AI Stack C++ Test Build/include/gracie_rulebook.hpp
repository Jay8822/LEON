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

// Mirrors agents/escalation_orchestrator.py's FaultClass -- EDEN's
// vocabulary, not GRACIE's own (EDEN herself is not ported, see this
// file's header). GracieRulebookState never reads these; it only
// carries them for EDEN's benefit, same boundary as the Python side.
// kNotStated is the C++ equivalent of Python's Optional[FaultClass]
// = None -- "this rule book doesn't state a class for this sense this
// round" is itself a valid, required answer, not a missing one (same
// "no invented numbers, but an honest non-claim is allowed" pattern
// as min_normal_noise<=0.0 below). Zero-value by construction, so a
// zero-initialized ChannelRule defaults every fault-class field to
// kNotStated without needing to set it explicitly.
enum class FaultClass : std::uint8_t {
    kNotStated = 0,
    kMajor = 1,
    kNonUrgent = 2,
    kBoom = 3,
};

// Mirrors agents/gracie.py's causing_sense vocabulary exactly (module
// docstring, point 14): which sense most recently raised
// latched_severity to its current value. kNone is Python's None.
// kJump deliberately does not exist -- jump never touches
// latched_severity (module docstring, point 3), so it can never be
// the cause of anything this enum describes.
enum class CausingSense : std::uint8_t {
    kNone = 0,
    kLevel = 1,
    kLeashSoft = 2,
    kLeashHard = 3,
    kStillness = 4,
    kClock = 5,
    kClockRepeated = 6,
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
    // Stillness (2026-11-06): a sensor's variation over
    // stuck_window_seconds must never fall below min_normal_noise, or
    // the sensor itself is suspect. min_normal_noise<=0.0 is the
    // explicit, stated way a caller disables this for a channel (see
    // process_stillness in the .cpp) -- not an invented real number.
    double stuck_window_seconds;
    double min_normal_noise;
    // Fault class per sense (2026-11-06, matching Python's Item C):
    // required fields, but kNotStated is an honest "not stated this
    // round" answer -- see the FaultClass comment above.
    FaultClass level_fault_class;
    FaultClass jump_fault_class;
    FaultClass leash_soft_fault_class;
    FaultClass leash_hard_fault_class;
    FaultClass stillness_fault_class;
    // Clock health (2026-11-05): N occurrences of a backward-jumped
    // timestamp within T seconds of each other escalates from a
    // single flagged event to a sustained one. No defaults -- set
    // from real hardware, same discipline as every limit above.
    FaultClass clock_fault_class;
    FaultClass clock_repeated_fault_class;
    int clock_fault_repeat_count;              // N
    double clock_fault_repeat_window_seconds;  // T
    // Other channels this one is linked to (by name, resolved by
    // lookup at check-time, not by index -- so registration order
    // never matters). An empty set is a genuine default (no claimed
    // relationship), same as the Python side's field(default_factory=tuple).
    FixedString linked_channel_names[kMaxLinkedChannels];
    int linked_channel_count;
    // Some sensors legitimately hold steady or step in some
    // conditions -- explicit opt-out from Stillness. Defaults to
    // false (most sensors are NOT exempt) via zero-init, same as the
    // Python side's allow_steady=False default.
    bool allow_steady;
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

    // Clock health (2026-11-05): the last timestamp seen for this
    // channel, checked before any sense uses a new one.
    bool has_last_timestamp;
    double last_timestamp;
    // Trusted-reference times of recent backward-jump occurrences,
    // for the N-within-T escalation -- each entry is the last
    // TRUSTED (forward-moving) timestamp immediately before that
    // occurrence, never the occurrence's own still-suspect one. Same
    // fixed-ring shape as the leash ring above, much smaller.
    double clock_fault_times[kMaxClockFaultOccurrences];
    int clock_fault_head;
    int clock_fault_count;

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

    // Stillness (2026-11-06): same ring-buffer shape as leash's above,
    // but needs the full spread of every value currently in the
    // window (min/max), not just two endpoints -- so it keeps its own
    // ring rather than reusing leash's anchor-only one. True from the
    // moment Stillness first triggers until clear_fault, same as the
    // Python side's stillness_active.
    LeashRingEntry stillness_ring[kStillnessRingCapacity];
    int stillness_ring_head;
    int stillness_ring_count;
    bool stillness_active;

    // Which sense most recently raised latched_severity to its
    // current (non-NOMINAL) value -- mirrors agents/gracie.py's
    // causing_sense exactly, including that it persists with the
    // latch (module docstring, point 14) until clear_fault or leash's
    // own self-settle exception clears it to kNone.
    CausingSense causing_sense;
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
    bool clock_event;                      // this reading's timestamp was earlier than the last one
    bool clock_repeated;                   // clock_event, and N occurrences fell within T seconds
    bool sensor_health_fault;              // Stillness: this channel's sensor itself is suspect (mirrors the Python report's "sensor_health_fault" key)
    CausingSense causing_sense;            // which sense most recently raised latched_severity
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
// matches agents/gracie.py's process_readings exactly: clock health
// first (2026-11-05 -- resets jump's last sample, leash's ring, and
// Stillness's ring before any of them ever sees an out-of-order
// timestamp), then level, then jump, then leash, then Stillness
// (2026-11-06) -- leash's "part of an active major fault" check reads
// latched_severity AFTER level has already run this same cycle, and
// Stillness's unconditional causing_sense overwrite (matching the
// Python side exactly) means whichever of level/leash/Stillness fires
// LAST this cycle wins the attribution, so this order is load-bearing,
// not incidental.
Status gracie_rulebook_process_reading(GracieRulebookState* state,
                                        int channel_index,
                                        double timestamp,
                                        double value,
                                        ProcessResult* out_result);

// Mirrors agents/gracie.py's clear_fault(channel, reset_leash_timer).
// Does NOT touch the leash ring buffer, the Stillness ring, or
// level_crossing_active -- same as the Python side, which only ever
// resets latched_severity, stillness_active, causing_sense,
// clock_fault_times, and (if reset_leash_timer) pull_run_start/
// soft_active/hard_active.
Status gracie_rulebook_clear_fault(GracieRulebookState* state,
                                    int channel_index,
                                    bool reset_leash_timer);

// Mirrors clear_fault(channel=None) -- clears every registered channel.
Status gracie_rulebook_clear_fault_all(GracieRulebookState* state,
                                        bool reset_leash_timer);

}  // namespace leon

#endif  // LEON_GRACIE_RULEBOOK_HPP
