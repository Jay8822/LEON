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

}  // namespace leon

#endif  // LEON_CONFIG_HPP
