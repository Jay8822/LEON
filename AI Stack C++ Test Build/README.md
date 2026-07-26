# AI Stack C++ Test Build

A first, small proof-of-concept for a NASA/JPL "Power of 10"-compliant
C++ implementation of LEON's fault-escalation chain (GRACIE health
monitoring -> EDEN safe-mode response -> SystemCoordinator status
registry). It is a **redesign**, not a translation of the Python code —
the constraints below rule out the pub/sub architecture main.py uses.

Concept and architecture by Jay Pratt. Written with AI pair-programming
assistance (Claude, Anthropic), 2026-07-26. **Not yet compiled or run**
— no C++ toolchain (g++/clang/cl/cmake) was available in the environment
this was written in. See "Status" below before trusting any of it.

## What "Power of 10" is

Gerard Holzmann's ten rules for safety-critical C, adopted at JPL for
flight software:

1. Avoid complex flow constructs — no `goto`, no recursion.
2. All loops must have fixed, provable bounds.
3. No dynamic memory allocation after initialization.
4. No function longer than what fits on one printed page (~60 lines).
5. Minimum two runtime assertions per function.
6. Declare data objects at the smallest possible scope.
7. Check the return value of every non-void function.
8. Limit preprocessor use to header guards and simple macros.
9. Restrict pointer use to one level of dereference; **no function pointers**.
10. Compile with every warning enabled and zero warnings; run a static analyzer daily.

## The one architectural decision that changes everything

Rule 9 bans function pointers outright. `std::function`, lambdas used as
callbacks, and virtual dispatch (a vtable call *is* a function-pointer
call under the hood) are all out. That's fatal for main.py's design:
`EventBus.subscribe(topic, handler)` is a registry of function pointers
by definition.

The compliant replacement used here is a **cyclic executive**: no bus,
no registration. `src/main.cpp` calls each agent's handler directly, in
a fixed, compile-time-known sequence, once per cycle:

```
telemetry -> gracie_process_telemetry() -> coordinator_on_gracie_health()
                                         -> eden_on_health_event() -> coordinator_on_eden_status()
```

This is how flight software actually schedules work (a fixed cycle,
not dynamic dispatch), so it's not just a workaround for Rule 9 — it's
the more representative design for what this would eventually need to
be.

## What's deliberately not here

HALIA's freeform chat/snark generation, the Flask web UI, and the
JSON-driven skills lookup don't belong in a Power-of-10 binary at all —
unbounded string generation, a web server, and runtime JSON parsing all
fight every rule above at once. If a crew-facing interface is needed
later, it'd be a small, fixed-response command interface, not a port of
HALIA as it exists in Python — and it would likely stay outside the
compliant core entirely, same as ground software does on real missions.

## Compliance checklist (this code, rule by rule)

| Rule | How it's satisfied here |
|---|---|
| 1. No goto/recursion | None used anywhere. |
| 2. Fixed loop bounds | `main.cpp`'s cycle loop runs `kSimCycles` times over a static array; `fixed_string_set`'s copy loop is capped at `kMaxReasonLen`. |
| 3. No heap after init | No `new`, no STL containers that allocate (`std::string`/`vector`/`map`). Fixed structs and C arrays only. |
| 4. Function length | Every function is under 40 lines. |
| 5. >=2 assertions/function | Every function asserts its pointer preconditions and, where meaningful, a postcondition. |
| 6. Minimal data scope | No global mutable state — every module's state is a struct passed explicitly by pointer. |
| 7. Checked returns | Every call site (`main.cpp`, `test_gracie.cpp`) checks the `Status` return and bails with a message on failure. |
| 8. Minimal preprocessor | Only `#ifndef`/`#define`/`#endif` header guards. |
| 9. No function pointers | No `std::function`, no lambdas-as-callbacks, no virtual functions — see the cyclic-executive note above. |
| 10. Warnings + static analysis | `CMakeLists.txt` sets `-Wall -Wextra -Wpedantic -Werror -Wconversion -Wshadow` (or `/W4 /WX` on MSVC) and wires up an optional `cppcheck` target. |

## Status — read before trusting this code

This was written without a compiler available to check it. It has been
reviewed carefully by hand for the usual mistakes (null checks before
dereference, correct bounds, matching signatures) but **has not
actually been built**. Treat it as a draft pending a real compile, not
verified working code.

## Building it (once you have a toolchain)

Requires a C++14 compiler and CMake 3.14+. If you don't have one:
- Windows: install [MSYS2](https://www.msys2.org/) (`pacman -S mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-cmake`) or Visual Studio's "Desktop development with C++" workload.
- Or WSL: `sudo apt install build-essential cmake`.

```
cmake -S . -B build
cmake --build build
./build/test_gracie      # or build\test_gracie.exe on Windows/MSVC
./build/leon_sim
```

If it doesn't compile cleanly, paste the errors back — first-pass C++
written without a compiler in the loop is exactly the kind of thing
that needs a real build to shake out.

## Roadmap, if this is worth continuing

1. Get this compiling clean with zero warnings — the real first
   milestone, not anything above.
2. Port LUNAE (navigation) and ETHAN (propulsion) as the same kind of
   fixed-state-struct modules, wired into the same cyclic executive.
3. Replace the hardcoded test telemetry with a real bounded input
   source (a fixed-size ring buffer fed by a sensor driver, still no
   heap).
4. Decide what, if anything, a crew-facing interface looks like under
   these constraints — almost certainly not a port of HALIA.
5. Get an actual static analyzer (cppcheck, or ideally a MISRA-aware
   one) and CI running before calling any of it flight-representative.
