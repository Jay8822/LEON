// src/gracie_rulebook.cpp
// AI Stack C++ Test Build — Jay Pratt + AI (Claude Sonnet 5, Anthropic). Added 2026-10-27.
// Ported branch-for-branch from agents/gracie.py -- see
// include/gracie_rulebook.hpp for exact scope.
#include "gracie_rulebook.hpp"

#include <cassert>
#include <cmath>

namespace leon {
namespace {

// --- leash ring buffer: fixed-size equivalent of the Python deque ---------

const LeashRingEntry& ring_at(const ChannelState& cs, int offset_from_oldest) {
    const int index = (cs.ring_head + offset_from_oldest) % kLeashRingCapacity;
    return cs.ring[index];
}

void ring_pop_front(ChannelState* cs) {
    cs->ring_head = (cs->ring_head + 1) % kLeashRingCapacity;
    cs->ring_count -= 1;
}

Status ring_push_back(ChannelState* cs, double timestamp, double value) {
    if (cs->ring_count >= kLeashRingCapacity) {
        return Status::kRingOverflow;
    }
    const int tail = (cs->ring_head + cs->ring_count) % kLeashRingCapacity;
    cs->ring[tail].timestamp = timestamp;
    cs->ring[tail].value = value;
    cs->ring_count += 1;
    return Status::kOk;
}

// Incremental equivalent of agents/gracie.py's
// _update_window_and_get_slope(): the ring's oldest entry is always
// the tightest valid anchor, trimmed from the front only while the
// *next* entry is still at least leash_window_seconds away from
// `timestamp` -- same two-pointer reasoning as the batch scripts'
// Fragment._windowed_slopes(), just incremental and bounded.
Status update_leash_window(ChannelState* cs, double timestamp, double value,
                            bool* out_has_slope, double* out_slope) {
    while (cs->ring_count >= 2) {
        const LeashRingEntry& second = ring_at(*cs, 1);
        if ((timestamp - second.timestamp) >= cs->rule.leash_window_seconds) {
            ring_pop_front(cs);
        } else {
            break;
        }
    }
    const Status push_status = ring_push_back(cs, timestamp, value);
    if (push_status != Status::kOk) {
        *out_has_slope = false;
        *out_slope = 0.0;
        return push_status;
    }
    const LeashRingEntry& anchor = ring_at(*cs, 0);
    const double dt = timestamp - anchor.timestamp;
    if (dt >= cs->rule.leash_window_seconds) {
        *out_has_slope = true;
        *out_slope = (value - anchor.value) / dt;
    } else {
        *out_has_slope = false;
        *out_slope = 0.0;
    }
    return Status::kOk;
}

// --- level, jump, leash: ported from agents/gracie.py's _process_* --------

// Mirrors _process_level, WITHOUT the `expected` branch (out of
// scope -- see file header). Always takes the "not expected" path,
// which is what every real-data test harness exercises anyway, since
// none of them pass expected_causes into this ported core's proof.
void process_level(ChannelState* cs, double value, bool* out_new_crossing_while_latched) {
    const ChannelRule& rule = cs->rule;
    const bool crossing = (value > rule.level_high) || (value < rule.level_low);
    *out_new_crossing_while_latched = false;
    if (!crossing) {
        cs->level_crossing_active = false;
        return;
    }
    const bool is_new_crossing = !cs->level_crossing_active;
    if (is_new_crossing && cs->latched_severity == Severity::kFault) {
        *out_new_crossing_while_latched = true;
    }
    cs->latched_severity = Severity::kFault;
    cs->level_crossing_active = true;
}

// Mirrors _process_jump: a momentary rate-of-change check, never
// latched.
bool process_jump(ChannelState* cs, double timestamp, double value) {
    if (!cs->has_last_sample) {
        cs->has_last_sample = true;
        cs->last_sample_timestamp = timestamp;
        cs->last_sample_value = value;
        return false;
    }
    const double last_t = cs->last_sample_timestamp;
    const double last_v = cs->last_sample_value;
    cs->last_sample_timestamp = timestamp;
    cs->last_sample_value = value;
    const double dt = timestamp - last_t;
    if (dt == 0.0) {
        return false;
    }
    return (std::fabs(value - last_v) / dt) > cs->rule.jump_limit;
}

// Mirrors _is_part_of_active_major_fault: this channel's own level
// FAULT is latched, or it's linked to another channel currently
// latched FAULT.
bool is_part_of_active_major_fault(const GracieRulebookState* state, int channel_index) {
    const ChannelState& cs = state->channels[channel_index];
    if (cs.latched_severity == Severity::kFault) {
        return true;
    }
    for (int i = 0; i < cs.rule.linked_channel_count; ++i) {
        int linked_index = -1;
        const Status found = gracie_rulebook_find_channel(
            state, cs.rule.linked_channel_names[i].data, &linked_index);
        if (found == Status::kOk && state->channels[linked_index].latched_severity == Severity::kFault) {
            return true;
        }
    }
    return false;
}

enum class LeashOutcome : std::uint8_t {
    kNone = 0,
    kSettled = 1,
};

// Mirrors _process_leash exactly, including the settle-back-unless-
// part-of-an-active-major-fault exception.
LeashOutcome process_leash(GracieRulebookState* state, int channel_index,
                            double timestamp, bool has_slope, double slope) {
    ChannelState* cs = &state->channels[channel_index];
    const ChannelRule& rule = cs->rule;

    if (!has_slope || std::fabs(slope) <= rule.leash_slope_limit) {
        const bool was_soft_only = cs->soft_active && !cs->hard_active;
        cs->has_pull_run_start = false;
        cs->soft_active = false;
        cs->hard_active = false;
        if (!was_soft_only) {
            return LeashOutcome::kNone;
        }
        if (is_part_of_active_major_fault(state, channel_index)) {
            return LeashOutcome::kNone;
        }
        cs->latched_severity = Severity::kNominal;
        return LeashOutcome::kSettled;
    }

    if (!cs->has_pull_run_start) {
        cs->has_pull_run_start = true;
        cs->pull_run_start = timestamp;
    }
    const double elapsed = timestamp - cs->pull_run_start;

    if (elapsed >= rule.leash_soft_duration_seconds && !cs->soft_active) {
        cs->soft_active = true;
        if (static_cast<int>(cs->latched_severity) < static_cast<int>(Severity::kWarning)) {
            cs->latched_severity = Severity::kWarning;
        }
    }
    if (elapsed >= rule.leash_hard_duration_seconds && !cs->hard_active) {
        cs->hard_active = true;
        if (static_cast<int>(cs->latched_severity) < static_cast<int>(Severity::kFault)) {
            cs->latched_severity = Severity::kFault;
        }
    }
    return LeashOutcome::kNone;
}

}  // namespace

Status gracie_rulebook_init(GracieRulebookState* state) {
    assert(state != nullptr);
    if (state == nullptr) {
        return Status::kInvalidArgument;
    }
    state->channel_count = 0;
    for (int i = 0; i < kMaxChannels; ++i) {
        state->channels[i] = ChannelState{};
    }
    return Status::kOk;
}

Status gracie_rulebook_add_channel(GracieRulebookState* state,
                                    const char* channel_name,
                                    const ChannelRule* rule,
                                    int* out_index) {
    assert(state != nullptr);
    assert(channel_name != nullptr);
    assert(rule != nullptr);
    assert(out_index != nullptr);
    if (state == nullptr || channel_name == nullptr || rule == nullptr || out_index == nullptr) {
        return Status::kInvalidArgument;
    }
    if (state->channel_count >= kMaxChannels) {
        return Status::kInvalidArgument;
    }
    const int index = state->channel_count;
    ChannelState* cs = &state->channels[index];
    *cs = ChannelState{};
    cs->rule = *rule;
    const Status name_status = fixed_string_set(&cs->rule.name, channel_name);
    if (name_status != Status::kOk) {
        return name_status;
    }
    state->channel_count = index + 1;
    *out_index = index;
    return Status::kOk;
}

Status gracie_rulebook_find_channel(const GracieRulebookState* state,
                                     const char* channel_name,
                                     int* out_index) {
    assert(state != nullptr);
    assert(channel_name != nullptr);
    assert(out_index != nullptr);
    if (state == nullptr || channel_name == nullptr || out_index == nullptr) {
        return Status::kInvalidArgument;
    }
    for (int i = 0; i < state->channel_count; ++i) {
        if (fixed_string_equals(&state->channels[i].rule.name, channel_name)) {
            *out_index = i;
            return Status::kOk;
        }
    }
    return Status::kInvalidArgument;
}

Status gracie_rulebook_process_reading(GracieRulebookState* state,
                                        int channel_index,
                                        double timestamp,
                                        double value,
                                        ProcessResult* out_result) {
    assert(state != nullptr);
    assert(out_result != nullptr);
    if (state == nullptr || out_result == nullptr ||
        channel_index < 0 || channel_index >= state->channel_count) {
        return Status::kInvalidArgument;
    }
    ChannelState* cs = &state->channels[channel_index];

    // Order matches agents/gracie.py's process_readings exactly:
    // level, then jump, then leash -- leash's active-major-fault
    // check reads latched_severity AFTER level has already run this
    // same cycle, so this order is load-bearing.
    bool new_crossing_while_latched = false;
    process_level(cs, value, &new_crossing_while_latched);

    const bool jump_event = process_jump(cs, timestamp, value);

    bool has_slope = false;
    double slope = 0.0;
    const Status ring_status = update_leash_window(cs, timestamp, value, &has_slope, &slope);
    if (ring_status != Status::kOk) {
        return ring_status;
    }

    const LeashOutcome leash_outcome = process_leash(state, channel_index, timestamp, has_slope, slope);

    out_result->severity = cs->latched_severity;
    out_result->jump_event = jump_event;
    out_result->leash_settled = (leash_outcome == LeashOutcome::kSettled);
    out_result->new_crossing_while_latched = new_crossing_while_latched;
    out_result->has_slope = has_slope;
    out_result->slope = slope;
    return Status::kOk;
}

Status gracie_rulebook_clear_fault(GracieRulebookState* state,
                                    int channel_index,
                                    bool reset_leash_timer) {
    assert(state != nullptr);
    if (state == nullptr || channel_index < 0 || channel_index >= state->channel_count) {
        return Status::kInvalidArgument;
    }
    ChannelState* cs = &state->channels[channel_index];
    cs->latched_severity = Severity::kNominal;
    if (reset_leash_timer) {
        cs->has_pull_run_start = false;
        cs->soft_active = false;
        cs->hard_active = false;
    }
    return Status::kOk;
}

Status gracie_rulebook_clear_fault_all(GracieRulebookState* state, bool reset_leash_timer) {
    assert(state != nullptr);
    if (state == nullptr) {
        return Status::kInvalidArgument;
    }
    for (int i = 0; i < state->channel_count; ++i) {
        const Status s = gracie_rulebook_clear_fault(state, i, reset_leash_timer);
        if (s != Status::kOk) {
            return s;
        }
    }
    return Status::kOk;
}

}  // namespace leon
