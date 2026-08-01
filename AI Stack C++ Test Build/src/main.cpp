// src/main.cpp
// AI Stack C++ Test Build — Jay Pratt + AI (Claude, Anthropic). Started 2026-07-26.
//
// This is a "cyclic executive": every cycle, each agent's handler is
// called directly, in a fixed, compile-time-known order. There is no
// event bus and no registration step. Power-of-10 Rule 9 ("no function
// pointers") rules out the callback-table pub/sub pattern main.py uses
// in the Python version — a subscriber list is fundamentally a list of
// function pointers. Static wiring here is the compliant replacement.
#include <cstdio>

#include "coordinator.hpp"
#include "eden.hpp"
#include "gracie.hpp"
#include "leon_config.hpp"
#include "leon_types.hpp"

namespace {

// Fixed, deterministic stand-in for real telemetry. Rule 2 requires
// provably-bounded loops; a flight build would read these values from
// sensor drivers, not a static array. The sequence below exercises the
// same NOMINAL -> WARNING -> FAULT -> (latched) path as
// agents/gracie_test.py and agents/test_halia_gracie.py.
//
// To be explicit: this is scripted test input, not staged output. It's
// fixed so the demo reproducibly walks NOMINAL -> WARNING -> FAULT on
// every run instead of depending on randomness. The fault-detection
// and escalation logic below (gracie_process_telemetry(),
// eden_on_health_event(), the coordinator calls) is the real,
// unmodified logic reacting live to whatever this array contains.
const leon::TelemetryPacket kTestTelemetry[leon::kSimCycles] = {
    {1000, 30.0f, 10.0f, 0.2f, leon::NavState::kCruise, leon::HealthState::kNominal},
    {1001, 45.0f, 20.0f, 0.3f, leon::NavState::kCruise, leon::HealthState::kNominal},
    {1002, 52.0f, 15.0f, 0.4f, leon::NavState::kCruise, leon::HealthState::kNominal},
    {1003, 56.0f, 45.0f, 0.5f, leon::NavState::kCruise, leon::HealthState::kNominal},
    {1004, 30.0f, 10.0f, 0.1f, leon::NavState::kCruise, leon::HealthState::kNominal},
    {1005, 30.0f, 10.0f, 0.1f, leon::NavState::kCruise, leon::HealthState::kNominal},
    {1006, 30.0f, 10.0f, 0.1f, leon::NavState::kCruise, leon::HealthState::kNominal},
    {1007, 30.0f, 10.0f, 0.1f, leon::NavState::kCruise, leon::HealthState::kNominal},
    {1008, 30.0f, 10.0f, 0.1f, leon::NavState::kCruise, leon::HealthState::kNominal},
    {1009, 30.0f, 10.0f, 0.1f, leon::NavState::kCruise, leon::HealthState::kNominal},
};

const char* health_name(leon::HealthState h) {
    switch (h) {
        case leon::HealthState::kNominal: return "NOMINAL";
        case leon::HealthState::kWarning: return "WARNING";
        case leon::HealthState::kFault:   return "FAULT";
    }
    return "UNKNOWN";
}

}  // namespace

int main() {
    leon::GracieState gracie_state{};
    leon::EdenState eden_state{};
    leon::SubsystemStatus coord_status{};

    if (leon::gracie_init(&gracie_state) != leon::Status::kOk) {
        std::fputs("gracie_init failed\n", stderr);
        return 1;
    }
    if (leon::eden_init(&eden_state) != leon::Status::kOk) {
        std::fputs("eden_init failed\n", stderr);
        return 1;
    }
    if (leon::coordinator_init(&coord_status) != leon::Status::kOk) {
        std::fputs("coordinator_init failed\n", stderr);
        return 1;
    }

    for (int i = 0; i < leon::kSimCycles; ++i) {
        const leon::TelemetryPacket& telemetry = kTestTelemetry[i];

        leon::HealthState health = leon::HealthState::kNominal;
        leon::Status s = leon::gracie_process_telemetry(&gracie_state, &telemetry, &health);
        if (s != leon::Status::kOk) {
            std::fprintf(stderr, "cycle %d: gracie_process_telemetry failed\n", i);
            return 1;
        }

        bool fault_transition = false;
        s = leon::coordinator_on_gracie_health(&coord_status, health, telemetry.timestamp, &fault_transition);
        if (s != leon::Status::kOk) {
            std::fprintf(stderr, "cycle %d: coordinator_on_gracie_health failed\n", i);
            return 1;
        }
        if (fault_transition) {
            std::printf("cycle %d: ALERT - GRACIE FAULT detected, notifying HALIA\n", i);
        }

        leon::CommandPacket command{};
        bool command_issued = false;
        s = leon::eden_on_health_event(&eden_state, health, &command, &command_issued);
        if (s != leon::Status::kOk) {
            std::fprintf(stderr, "cycle %d: eden_on_health_event failed\n", i);
            return 1;
        }

        s = leon::coordinator_on_eden_status(&coord_status, eden_state.status, telemetry.timestamp);
        if (s != leon::Status::kOk) {
            std::fprintf(stderr, "cycle %d: coordinator_on_eden_status failed\n", i);
            return 1;
        }

        if (command_issued) {
            std::printf("cycle %d: GRACIE=%s EDEN=SAFE_MODE_ISSUED reason=%s\n",
                        i, health_name(health), command.reason.data);
        } else {
            std::printf("cycle %d: GRACIE=%s EDEN=MONITORING\n", i, health_name(health));
        }
    }

    return 0;
}
