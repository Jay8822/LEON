// include/gracie.hpp
// AI Stack C++ Test Build — Jay Pratt + AI (Claude, Anthropic). Started 2026-07-26.
#ifndef LEON_GRACIE_HPP
#define LEON_GRACIE_HPP

#include "leon_types.hpp"

namespace leon {

// All mutable state lives in this struct, passed explicitly by pointer
// to every function (Rule 6: smallest possible scope, no hidden global
// state; Rule 9: no virtual dispatch needed since there's no interface
// to implement).
struct GracieState {
    HealthState health;
};

Status gracie_init(GracieState* state);

// FAULT latches until gracie_clear_fault() — a single recovered reading
// must not mask a fault the operator hasn't acknowledged.
Status gracie_process_telemetry(GracieState* state,
                                 const TelemetryPacket* telemetry,
                                 HealthState* out_health);

Status gracie_clear_fault(GracieState* state);

}  // namespace leon

#endif  // LEON_GRACIE_HPP
