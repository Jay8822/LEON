// include/coordinator.hpp
// AI Stack C++ Test Build — Jay Pratt + AI (Claude, Anthropic). Started 2026-07-26.
#ifndef LEON_COORDINATOR_HPP
#define LEON_COORDINATOR_HPP

#include "eden.hpp"
#include "leon_types.hpp"

namespace leon {

struct SubsystemStatus {
    HealthState gracie_health;
    EdenStatus eden_status;
    std::uint32_t last_update_gracie;
    std::uint32_t last_update_eden;
};

Status coordinator_init(SubsystemStatus* status);

// out_fault_transition is true only on the cycle health first becomes
// FAULT, not on every repeat FAULT reading — mirrors the 2026-07-26 fix
// to agents/system_coordinator.py, which used to re-alert every cycle.
Status coordinator_on_gracie_health(SubsystemStatus* status,
                                     HealthState health,
                                     std::uint32_t timestamp,
                                     bool* out_fault_transition);

Status coordinator_on_eden_status(SubsystemStatus* status,
                                   EdenStatus eden_status,
                                   std::uint32_t timestamp);

}  // namespace leon

#endif  // LEON_COORDINATOR_HPP
