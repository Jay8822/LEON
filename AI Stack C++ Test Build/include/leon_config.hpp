// include/leon_config.hpp
// AI Stack C++ Test Build — Jay Pratt + AI (Claude, Anthropic). Started 2026-07-26.
#ifndef LEON_CONFIG_HPP
#define LEON_CONFIG_HPP

namespace leon {

// Fixed capacities. Power-of-10 Rule 3 (no dynamic allocation after
// init) means every buffer needs a compile-time-known upper bound
// instead of a Python list/dict that grows freely.
constexpr int kMaxReasonLen = 32;  // e.g. "GRACIE_FAULT"
constexpr int kSimCycles = 10;     // matches the Python demo's 10-cycle run

// gracie_rulebook (2026-10-27): per-channel rule-book GRACIE core,
// ported from agents/gracie.py. Fixed capacities, stated as design
// limits (Power-of-10 Rule 3 -- no allocation after init).
constexpr int kMaxChannels = 64;         // comfortably covers every real-data run so far
constexpr int kMaxLinkedChannels = 8;    // ChannelRule.linked_channels, Python side has no cap but every real/test rule book uses <=1
// Leash's windowed slope needs a sliding history of (timestamp, value)
// pairs covering the last leash_window_seconds -- Python's deque is
// unbounded; real data is bursty (one ESA-ADB channel needs up to
// ~1,200 entries within a 3600s window in the worst case actually
// measured), so this is sized with headroom over that, not guessed.
// If a dataset ever needs more than this, gracie_rulebook_process_reading
// returns Status::kRingOverflow -- reported, never silently truncated.
constexpr int kLeashRingCapacity = 2048;

// Clock health (2026-11-05, Ccode update.txt "CLOCK-FAULT PLAN"): a
// small ring of recent backward-jump occurrence times, for the
// N-within-T-seconds escalation. N (ChannelRule.clock_fault_repeat_
// count) is a rule-book value set from real hardware, with no
// measured worst case yet -- unlike kLeashRingCapacity above, this is
// generous headroom over any plausible N (expected single digits),
// not a measured figure. Same reporting if ever exceeded:
// Status::kRingOverflow, never silently truncated.
constexpr int kMaxClockFaultOccurrences = 32;

// Stillness (2026-11-06, "C++: PORT STILLNESS + FAULT CLASSES"): a
// sliding window of recent (timestamp, value) pairs covering the last
// stuck_window_seconds, needed to find the window's full value spread
// (min/max), not just two endpoints like leash's ring above. Every
// real-data test harness so far sets stuck_window_seconds equal to
// leash_window_seconds (same window, same channel -- confirmed by
// reading real_data_tests/esa_adb/'s and cpp_proof/'s own rule
// derivation), so leash's own measured worst-case burst count applies
// identically here -- reused, not guessed. Same reporting if ever
// exceeded: Status::kRingOverflow, never silently truncated.
constexpr int kStillnessRingCapacity = kLeashRingCapacity;

}  // namespace leon

#endif  // LEON_CONFIG_HPP
