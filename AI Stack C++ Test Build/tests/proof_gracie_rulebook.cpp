// tests/proof_gracie_rulebook.cpp
// AI Stack C++ Test Build — Jay Pratt + AI (Claude Sonnet 5, Anthropic). Added 2026-10-27.
//
// Cross-language equivalence proof tool, NOT part of the Power-of-10
// core: reads one channel's already-derived rule-book values (a plain
// key=value sidecar file) and its readings (a plain CSV, with a
// per-row flag for whether a day-boundary clear_fault(reset_leash_
// timer=false) should fire before that reading, matching the real
// test harnesses' own driving pattern), replays them through the
// ported gracie_rulebook core, and writes a verdict log in the same
// shape a paired Python script writes from the real GracieAgent, for
// a Python diff script to compare line-for-line. This proves the
// DETECTION/latching logic only -- rule-book values are exported from
// Python's already-derived numbers, not re-derived here.
//
// Ordinary C++ (std::string/std::vector/streams) is used here, unlike
// gracie_rulebook.hpp/cpp itself -- this is offline test tooling, not
// the ported core, so Power-of-10's fixed-memory rule doesn't apply
// to it. Still compiles clean under this build's strict warning flags.
#include <cstdio>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <string>
#include <vector>

#include "gracie_rulebook.hpp"

namespace {

struct SidecarRule {
    double level_high = 0.0;
    double level_low = 0.0;
    double jump_limit = 0.0;
    double leash_window_seconds = 0.0;
    double leash_slope_limit = 0.0;
    double leash_soft_duration_seconds = 0.0;
    double leash_hard_duration_seconds = 0.0;
    std::vector<std::string> linked_channels;
};

bool load_sidecar(const std::string& path, SidecarRule* out) {
    std::ifstream f(path);
    if (!f.is_open()) {
        return false;
    }
    std::string line;
    while (std::getline(f, line)) {
        if (line.empty()) {
            continue;
        }
        const std::size_t eq = line.find('=');
        if (eq == std::string::npos) {
            continue;
        }
        const std::string key = line.substr(0, eq);
        const std::string val = line.substr(eq + 1);
        if (key == "level_high") {
            out->level_high = std::stod(val);
        } else if (key == "level_low") {
            out->level_low = std::stod(val);
        } else if (key == "jump_limit") {
            out->jump_limit = std::stod(val);
        } else if (key == "leash_window_seconds") {
            out->leash_window_seconds = std::stod(val);
        } else if (key == "leash_slope_limit") {
            out->leash_slope_limit = std::stod(val);
        } else if (key == "leash_soft_duration_seconds") {
            out->leash_soft_duration_seconds = std::stod(val);
        } else if (key == "leash_hard_duration_seconds") {
            out->leash_hard_duration_seconds = std::stod(val);
        } else if (key == "linked_channels") {
            if (!val.empty()) {
                std::stringstream ss(val);
                std::string item;
                while (std::getline(ss, item, ',')) {
                    if (!item.empty()) {
                        out->linked_channels.push_back(item);
                    }
                }
            }
        }
    }
    return true;
}

struct Reading {
    long long sample_index = 0;
    double timestamp = 0.0;
    double value = 0.0;
    bool clear_before = false;
};

bool load_readings(const std::string& path, std::vector<Reading>* out) {
    std::ifstream f(path);
    if (!f.is_open()) {
        return false;
    }
    std::string line;
    std::getline(f, line);  // header, discarded
    while (std::getline(f, line)) {
        if (line.empty()) {
            continue;
        }
        std::stringstream ss(line);
        std::string field;
        Reading r{};
        std::getline(ss, field, ',');
        r.sample_index = std::stoll(field);
        std::getline(ss, field, ',');
        r.timestamp = std::stod(field);
        std::getline(ss, field, ',');
        r.value = std::stod(field);
        std::getline(ss, field, ',');
        r.clear_before = (field == "1");
        out->push_back(r);
    }
    return true;
}

const char* severity_name(leon::Severity s) {
    switch (s) {
        case leon::Severity::kNominal: return "NOMINAL";
        case leon::Severity::kWarning: return "WARNING";
        case leon::Severity::kFault:   return "FAULT";
    }
    return "UNKNOWN";
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 4) {
        std::fprintf(stderr, "usage: proof_gracie_rulebook <sidecar.txt> <readings.csv> <out_verdicts.csv>\n");
        return 1;
    }

    SidecarRule sidecar;
    if (!load_sidecar(argv[1], &sidecar)) {
        std::fprintf(stderr, "failed to read sidecar: %s\n", argv[1]);
        return 1;
    }
    std::vector<Reading> readings;
    if (!load_readings(argv[2], &readings)) {
        std::fprintf(stderr, "failed to read readings: %s\n", argv[2]);
        return 1;
    }

    // static: GracieRulebookState is ~2.1MB (kLeashRingCapacity x
    // kMaxChannels) -- far too large for a default thread stack
    // (~1MB on Windows), so it must not be a plain stack local. Same
    // reasoning applies to any future caller, including a cyclic-
    // executive wiring -- see gracie_rulebook.hpp's struct comment.
    static leon::GracieRulebookState state{};
    if (leon::gracie_rulebook_init(&state) != leon::Status::kOk) {
        std::fprintf(stderr, "init failed\n");
        return 1;
    }

    leon::ChannelRule rule{};
    rule.level_high = sidecar.level_high;
    rule.level_low = sidecar.level_low;
    rule.jump_limit = sidecar.jump_limit;
    rule.leash_window_seconds = sidecar.leash_window_seconds;
    rule.leash_slope_limit = sidecar.leash_slope_limit;
    rule.leash_soft_duration_seconds = sidecar.leash_soft_duration_seconds;
    rule.leash_hard_duration_seconds = sidecar.leash_hard_duration_seconds;
    rule.linked_channel_count = 0;
    const std::size_t max_linked = static_cast<std::size_t>(leon::kMaxLinkedChannels);
    for (std::size_t i = 0; i < sidecar.linked_channels.size() && i < max_linked; ++i) {
        leon::fixed_string_set(&rule.linked_channel_names[i], sidecar.linked_channels[i].c_str());
        rule.linked_channel_count += 1;
    }

    int channel_index = -1;
    if (leon::gracie_rulebook_add_channel(&state, "proof_channel", &rule, &channel_index) != leon::Status::kOk) {
        std::fprintf(stderr, "add_channel failed\n");
        return 1;
    }

    std::ofstream out(argv[3]);
    if (!out.is_open()) {
        std::fprintf(stderr, "failed to open output: %s\n", argv[3]);
        return 1;
    }
    // 17 significant decimal digits round-trips an IEEE754 double
    // exactly. ostream's default precision (6) silently truncated
    // this on the first run -- caught by comparing against the
    // Python reference, not assumed correct.
    out << std::setprecision(17);
    out << "sample_index,severity,jump_event,leash_settled,new_crossing_while_latched,has_slope,slope\n";

    for (const Reading& r : readings) {
        if (r.clear_before) {
            if (leon::gracie_rulebook_clear_fault(&state, channel_index, false) != leon::Status::kOk) {
                std::fprintf(stderr, "clear_fault failed at sample %lld\n", r.sample_index);
                return 1;
            }
        }
        leon::ProcessResult result{};
        const leon::Status s = leon::gracie_rulebook_process_reading(
            &state, channel_index, r.timestamp, r.value, &result);
        if (s == leon::Status::kRingOverflow) {
            std::fprintf(stderr, "RING OVERFLOW at sample %lld -- real divergence, not handled\n",
                         r.sample_index);
            return 2;
        }
        if (s != leon::Status::kOk) {
            std::fprintf(stderr, "process_reading failed at sample %lld\n", r.sample_index);
            return 1;
        }
        out << r.sample_index << ',' << severity_name(result.severity) << ','
            << (result.jump_event ? 1 : 0) << ',' << (result.leash_settled ? 1 : 0) << ','
            << (result.new_crossing_while_latched ? 1 : 0) << ',' << (result.has_slope ? 1 : 0) << ','
            << result.slope << '\n';
    }
    std::printf("Processed %zu readings -> %s\n", readings.size(), argv[3]);
    return 0;
}
