// include/leon_types.hpp
// AI Stack C++ Test Build — Jay Pratt + AI (Claude, Anthropic). Started 2026-07-26.
#ifndef LEON_TYPES_HPP
#define LEON_TYPES_HPP

#include <cstdint>

#include "leon_config.hpp"

namespace leon {

// Every non-void function returns one of these and every call site
// checks it (Power-of-10 Rule 7). No exceptions: Rule 1 treats the
// non-local control transfer they introduce as a form of the "complex
// flow constructs" the rule forbids.
enum class Status : std::uint8_t {
    kOk = 0,
    kInvalidArgument = 1,
    // gracie_rulebook's leash ring buffer is fixed-size (Rule 3); this
    // is returned instead of silently dropping the oldest unflushed
    // entry when a dataset's sampling genuinely needs more capacity
    // than provisioned. See leon_config.hpp's kLeashRingCapacity.
    kRingOverflow = 2,
};

enum class HealthState : std::uint8_t {
    kNominal = 0,
    kWarning = 1,
    kFault = 2,
};

enum class NavState : std::uint8_t {
    kIdle = 0,
    kCruise = 1,
    kHold = 2,
};

enum class PropulsionMode : std::uint8_t {
    kIdle = 0,
    kNtp = 1,
    kNep = 2,
    kPlasma = 3,
    kSafeMode = 4,
};

// Stands in for a bounded C string. Not std::string: Rule 3 forbids the
// heap allocation std::string can still trigger on growth.
struct FixedString {
    char data[kMaxReasonLen];
    std::uint8_t length;
};

// Bounded copy — the loop is capped at kMaxReasonLen (Rule 2: fixed
// loop bounds), unlike strcpy/strcat which will walk off the end of
// whatever src happens to contain.
Status fixed_string_set(FixedString* out, const char* src);

// Bounded comparison against a plain C string, same Rule 2 loop cap
// as fixed_string_set. Used by gracie_rulebook's by-name channel
// lookup (a fixed, small (<=64) linear scan, not a map/hash).
bool fixed_string_equals(const FixedString* fs, const char* src);

struct TelemetryPacket {
    std::uint32_t timestamp;
    float temp_c;
    float radiation;
    float thrust_demand;
    NavState nav_state;
    HealthState system_health;
};

struct CommandPacket {
    enum class Command : std::uint8_t {
        kSafeMode = 0,
        kPropulsionSet = 1,
        kNavAdjust = 2,
    };

    Command command;
    PropulsionMode mode;
    FixedString reason;
};

}  // namespace leon

#endif  // LEON_TYPES_HPP
