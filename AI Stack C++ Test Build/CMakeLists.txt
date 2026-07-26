# CMakeLists.txt
# AI Stack C++ Test Build — Jay Pratt + AI (Claude, Anthropic). Started 2026-07-26.
cmake_minimum_required(VERSION 3.14)
project(AiStackCppTestBuild CXX)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Power-of-10 Rule 10: compile with every warning on, and treat warnings
# as errors so nothing merges with one left unaddressed.
if(MSVC)
    add_compile_options(/W4 /WX)
else()
    add_compile_options(-Wall -Wextra -Wpedantic -Werror -Wconversion -Wshadow)
    # No exceptions, no RTTI: neither fits the Power-of-10 control-flow
    # model (Rule 1), and both pull in runtime support this project
    # doesn't otherwise need. Not applied under MSVC here — disabling
    # /EHsc there needs more care with the standard headers, and this
    # hasn't been build-tested on MSVC. Left as a follow-up.
    add_compile_options(-fno-exceptions -fno-rtti)
endif()

add_library(leon_core STATIC
    src/leon_types.cpp
    src/gracie.cpp
    src/eden.cpp
    src/coordinator.cpp
)
target_include_directories(leon_core PUBLIC include)

add_executable(leon_sim src/main.cpp)
target_link_libraries(leon_sim PRIVATE leon_core)

add_executable(test_gracie tests/test_gracie.cpp)
target_link_libraries(test_gracie PRIVATE leon_core)

enable_testing()
add_test(NAME gracie_health_state COMMAND test_gracie)

# Power-of-10 Rule 10 also calls for a static analyzer run daily. Wired
# up here but not run automatically — cppcheck isn't installed in every
# environment (it wasn't in the one this was written in).
find_program(CPPCHECK cppcheck)
if(CPPCHECK)
    # --enable=all also pulls in the "information" category, which is
    # meta-commentary about the analysis itself (e.g. "limiting branch
    # analysis, use --check-level=exhaustive") rather than a finding
    # about the code — combined with --error-exitcode that fails the
    # build on pure noise. warning/style/performance/portability is
    # the set that actually flags code issues.
    add_custom_target(cppcheck
        COMMAND ${CPPCHECK} --enable=warning,style,performance,portability
                --std=c++14 --suppress=missingIncludeSystem
                --error-exitcode=1 -I ${CMAKE_SOURCE_DIR}/include
                ${CMAKE_SOURCE_DIR}/src ${CMAKE_SOURCE_DIR}/tests
    )
endif()
