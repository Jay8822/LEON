// src/gracie.cpp
// AI Stack C++ Test Build — Jay Pratt + AI (Claude, Anthropic). Started 2026-07-26.
#include "gracie.hpp"

#include <cassert>

namespace leon {

Status gracie_init(GracieState* state) {
    assert(state != nullptr);
    if (state == nullptr) {
        return Status::kInvalidArgument;
    }
    state->health = HealthState::kNominal;
    assert(state->health == HealthState::kNominal);
    return Status::kOk;
}

Status gracie_process_telemetry(GracieState* state,
                                 const TelemetryPacket* telemetry,
                                 HealthState* out_health) {
    assert(state != nullptr);
    assert(telemetry != nullptr);
    if (state == nullptr || telemetry == nullptr || out_health == nullptr) {
        return Status::kInvalidArgument;
    }

    // Mirrors the 2026-07-26 fix to agents/gracie.py: FAULT latches
    // until an explicit clear, and WARNING no longer gets silently
    // overwritten back to NOMINAL by the next check in the same pass.
    const bool fault_reading = telemetry->temp_c > 55.0f && telemetry->radiation > 40.0f;
    const bool warning_reading = telemetry->temp_c > 50.0f || telemetry->radiation > 30.0f;

    if (fault_reading) {
        state->health = HealthState::kFault;
    } else if (state->health != HealthState::kFault) {
        state->health = warning_reading ? HealthState::kWarning : HealthState::kNominal;
    }

    *out_health = state->health;
    return Status::kOk;
}

Status gracie_clear_fault(GracieState* state) {
    assert(state != nullptr);
    if (state == nullptr) {
        return Status::kInvalidArgument;
    }
    state->health = HealthState::kNominal;
    assert(state->health == HealthState::kNominal);
    return Status::kOk;
}

}  // namespace leon
