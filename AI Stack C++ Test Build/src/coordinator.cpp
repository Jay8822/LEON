// src/coordinator.cpp
// AI Stack C++ Test Build — Jay Pratt + AI (Claude, Anthropic). Started 2026-07-26.
#include "coordinator.hpp"

#include <cassert>

namespace leon {

Status coordinator_init(SubsystemStatus* status) {
    assert(status != nullptr);
    if (status == nullptr) {
        return Status::kInvalidArgument;
    }
    status->gracie_health = HealthState::kNominal;
    status->eden_status = EdenStatus::kIdle;
    status->last_update_gracie = 0;
    status->last_update_eden = 0;
    assert(status->gracie_health == HealthState::kNominal);
    return Status::kOk;
}

Status coordinator_on_gracie_health(SubsystemStatus* status,
                                     HealthState health,
                                     std::uint32_t timestamp,
                                     bool* out_fault_transition) {
    assert(status != nullptr);
    assert(out_fault_transition != nullptr);
    if (status == nullptr || out_fault_transition == nullptr) {
        return Status::kInvalidArgument;
    }

    const bool was_fault = (status->gracie_health == HealthState::kFault);
    *out_fault_transition = (health == HealthState::kFault) && !was_fault;

    status->gracie_health = health;
    status->last_update_gracie = timestamp;
    return Status::kOk;
}

Status coordinator_on_eden_status(SubsystemStatus* status,
                                   EdenStatus eden_status,
                                   std::uint32_t timestamp) {
    assert(status != nullptr);
    if (status == nullptr) {
        return Status::kInvalidArgument;
    }
    status->eden_status = eden_status;
    status->last_update_eden = timestamp;
    assert(status->eden_status == eden_status);
    return Status::kOk;
}

}  // namespace leon
