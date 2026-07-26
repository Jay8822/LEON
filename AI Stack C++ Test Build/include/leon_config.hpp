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

}  // namespace leon

#endif  // LEON_CONFIG_HPP
