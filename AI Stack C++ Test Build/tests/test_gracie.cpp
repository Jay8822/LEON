// tests/test_gracie.cpp
// AI Stack C++ Test Build — Jay Pratt + AI (Claude, Anthropic). Started 2026-07-26.
// Mirrors agents/gracie_test.py's cases exactly, so the two
// implementations can be checked against each other by eye.
#include <cassert>
#include <cstdio>
#include <cstdlib>

#include "gracie.hpp"

namespace {

void expect_health(leon::GracieState* state, float temp, float rad,
                    leon::HealthState expected, const char* label) {
    leon::TelemetryPacket telemetry{};
    telemetry.timestamp = 0;
    telemetry.temp_c = temp;
    telemetry.radiation = rad;
    telemetry.thrust_demand = 0.0f;
    telemetry.nav_state = leon::NavState::kCruise;
    telemetry.system_health = leon::HealthState::kNominal;

    leon::HealthState health = leon::HealthState::kNominal;
    const leon::Status s = leon::gracie_process_telemetry(state, &telemetry, &health);
    assert(s == leon::Status::kOk);
    if (s != leon::Status::kOk || health != expected) {
        std::fprintf(stderr, "FAIL: %s\n", label);
        std::exit(1);
    }
    std::printf("  ok: %s\n", label);
}

}  // namespace

int main() {
    leon::GracieState state{};
    if (leon::gracie_init(&state) != leon::Status::kOk) {
        std::fputs("gracie_init failed\n", stderr);
        return 1;
    }

    expect_health(&state, 30.0f, 10.0f, leon::HealthState::kNominal, "temp=30 rad=10 -> NOMINAL");
    expect_health(&state, 52.0f, 10.0f, leon::HealthState::kWarning, "temp=52 rad=10 -> WARNING");
    expect_health(&state, 56.0f, 41.0f, leon::HealthState::kFault,   "temp=56 rad=41 -> FAULT");
    expect_health(&state, 30.0f, 10.0f, leon::HealthState::kFault,   "temp=30 rad=10 (latched) -> FAULT");

    if (leon::gracie_clear_fault(&state) != leon::Status::kOk) {
        std::fputs("gracie_clear_fault failed\n", stderr);
        return 1;
    }
    if (state.health != leon::HealthState::kNominal) {
        std::fputs("FAIL: clear_fault did not reset to NOMINAL\n", stderr);
        return 1;
    }
    std::printf("  ok: clear_fault -> NOMINAL\n");

    std::printf("All GRACIE health-state checks passed.\n");
    return 0;
}
