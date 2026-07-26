// src/leon_types.cpp
// AI Stack C++ Test Build — Jay Pratt + AI (Claude, Anthropic). Started 2026-07-26.
#include "leon_types.hpp"

#include <cassert>

namespace leon {

Status fixed_string_set(FixedString* out, const char* src) {
    assert(out != nullptr);
    assert(src != nullptr);
    if (out == nullptr || src == nullptr) {
        return Status::kInvalidArgument;
    }

    std::uint8_t i = 0;
    for (; i < kMaxReasonLen - 1 && src[i] != '\0'; ++i) {
        out->data[i] = src[i];
    }
    out->data[i] = '\0';
    out->length = i;

    assert(out->length < kMaxReasonLen);
    return Status::kOk;
}

}  // namespace leon
