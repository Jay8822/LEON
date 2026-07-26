// src/eden.cpp
// AI Stack C++ Test Build — Jay Pratt + AI (Claude, Anthropic). Started 2026-07-26.
#include "eden.hpp"

#include <cassert>

namespace leon {

Status eden_init(EdenState* state) {
    assert(state != nullptr);
    if (state == nullptr) {
        return Status::kInvalidArgument;
    }
    state->status = EdenStatus::kIdle;
    assert(state->status == EdenStatus::kIdle);
    return Status::kOk;
}

Status eden_on_health_event(EdenState* state,
                             HealthState health,
                             CommandPacket* out_command,
                             bool* out_command_issued) {
    assert(state != nullptr);
    assert(out_command_issued != nullptr);
    if (state == nullptr || out_command == nullptr || out_command_issued == nullptr) {
        return Status::kInvalidArgument;
    }

    *out_command_issued = false;

    if (health == HealthState::kFault) {
        state->status = EdenStatus::kSafeMode;
        out_command->command = CommandPacket::Command::kSafeMode;
        out_command->mode = PropulsionMode::kSafeMode;
        const Status s = fixed_string_set(&out_command->reason, "GRACIE_FAULT");
        if (s != Status::kOk) {
            return s;
        }
        *out_command_issued = true;
    } else {
        state->status = EdenStatus::kMonitoring;
    }

    return Status::kOk;
}

}  // namespace leon
