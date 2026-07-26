// include/eden.hpp
// AI Stack C++ Test Build — Jay Pratt + AI (Claude, Anthropic). Started 2026-07-26.
#ifndef LEON_EDEN_HPP
#define LEON_EDEN_HPP

#include "leon_types.hpp"

namespace leon {

enum class EdenStatus : std::uint8_t {
    kIdle = 0,
    kMonitoring = 1,
    kSafeMode = 2,
};

struct EdenState {
    EdenStatus status;
};

Status eden_init(EdenState* state);

// Called once per telemetry cycle with GRACIE's latest verdict — not
// just when a command is issued. Mirrors the 2026-07-26 fix to
// agents/eden.py where EDEN only reported status from on_command(),
// so the coordinator's view of EDEN lagged behind GRACIE/LUNAE, which
// report every cycle.
Status eden_on_health_event(EdenState* state,
                             HealthState health,
                             CommandPacket* out_command,
                             bool* out_command_issued);

}  // namespace leon

#endif  // LEON_EDEN_HPP
