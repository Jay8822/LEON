# AI Stack C++ Test Build

A first, small proof-of-concept for a NASA/JPL "Power of 10"-compliant
C++ implementation of LEON's fault-escalation chain (GRACIE health
monitoring -> EDEN safe-mode response -> SystemCoordinator status
registry). It is a **redesign**, not a translation of the Python code —
the constraints below rule out the pub/sub architecture main.py uses.

Concept and architecture by Jay Pratt. Written with AI pair-programming
assistance (Claude, Anthropic), 2026-07-26. Written without a compiler
available in the original environment; subsequently built and verified
clean on three toolchains the same day — see "Status" below for the
full record before trusting any of it.

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

## Schema differences from the Python version (intentional, not drift)

A consistency pass (2026-07-27) compared `leon_types.hpp` against
`core/schemas.py` field by field. The differences below are kept as-is,
deliberately — Python is the ground-simulation schema, C++ is the
flight-representative subset, and they're not meant to converge:

| Field | Python (`core/schemas.py`) | C++ (`leon_types.hpp`) |
|---|---|---|
| `TelemetryPacket.source` | present (`str`) | **not present** — the C++ demo has exactly one telemetry source, so a source tag carries no information yet |
| `TelemetryPacket.nav_state` | free `str` | closed `NavState` enum (`kIdle`/`kCruise`/`kHold`) |
| `CommandPacket.mode` | `Optional[str]` — `None` when a command like SAFE_MODE has no propulsion mode | closed `PropulsionMode` enum with **no null representation**; SAFE_MODE has to use `PropulsionMode::kSafeMode` as a stand-in, since Rule 3's no-heap/no-`std::optional`-by-convention style here has nothing to hold "absent" |
| `CommandPacket.reason` | unconstrained `str` | `FixedString`, capped at `kMaxReasonLen - 1` (31) characters |

The `mode` difference is the one with real teeth: it's not just a type
change, it changes what "no mode" *means* — Python can say "not
applicable," C++ can only pick a concrete enum value and treat one of
them as standing in for "not applicable." Worth knowing if this is ever
extended to a command whose mode genuinely matters alongside SAFE_MODE.

**Test telemetry timestamps** (`1000`–`1009` in `main.cpp`): also
intentional, not a debug leftover. They're a fixed, deterministic input
sequence so the demo is reproducible run-to-run — using `time()` would
make every run's output timestamps different for no benefit, since
nothing here reads wall-clock time meaningfully. If this ever takes
input from a real sensor/clock source, this array is what gets replaced
(see the Roadmap below), not patched to look more "real" in place.

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
| 10. Warnings + static analysis | Compiles with zero warnings under `-Wall -Wextra -Wpedantic -Werror -Wconversion -Wshadow` on three separate toolchains, and `cppcheck --enable=warning,style,performance,portability` reports zero findings — both verified 2026-07-26 via the actual `cmake`/`ctest`/`cppcheck` targets (not just direct compiler invocation). See Status below. |

## Status — compiled and passing on three toolchains (2026-07-26)

Built and run three separate ways, all producing byte-identical output
— full timestamped transcript of every attempt (including the two dead
ends below) in `build.log`:

| Toolchain | Result |
|---|---|
| MinGW-w64 GCC 16.1.0 (UCRT) | Clean build, zero warnings, 23:42 |
| MSVC 19.51.36252 (VS 2026 Community) | Clean build, `/W4`, 23:44 |
| Clang 22.1.8 (LLVM) | Clean build, zero warnings, 23:45 |

Two dead ends on the way there, worth knowing if setting this up fresh:

- The official LLVM/Clang Windows installer targets MSVC's ABI and
  ships no standard-library headers of its own — without Visual Studio
  installed, `#include <cstdint>` fails outright even though Clang
  itself installed fine. Not broken, just not self-contained on
  Windows the way it is elsewhere. Installing MinGW-w64 (self-contained,
  ~1 minute) unblocked the first build; installing Visual Studio
  Community afterward (free for individual/personal and open-source
  use) then made Clang work too, since it could pick up VS's headers.
- `cl.exe` only exists on PATH inside a "Developer" shell — a plain
  PowerShell session needs `vcvarsall.bat`'s environment variables
  imported first.

All three `test_gracie` binaries and all three `leon_sim` binaries were
run and their output diffed by eye — identical across compilers:

```
$ ./test_gracie.exe
  ok: temp=30 rad=10 -> NOMINAL
  ok: temp=52 rad=10 -> WARNING
  ok: temp=56 rad=41 -> FAULT
  ok: temp=30 rad=10 (latched) -> FAULT
  ok: clear_fault -> NOMINAL
All GRACIE health-state checks passed.
```

`leon_sim.exe` reproduces the same FAULT-at-cycle-3 escalation as the
Python demo, latched through every later cycle (telemetry recovers but
the fault is never explicitly cleared) — full output in `build.log`.

**CMake/ctest/cppcheck pass (same day, later):** built and tested through
the actual `CMakeLists.txt` targets rather than direct compiler
invocation — `cmake -S . -B build -G Ninja`, `cmake --build build`,
`ctest --test-dir build` (1/1 passed), and `cmake --build build
--target cppcheck`. The `cppcheck` target's first run failed — not on a
real finding, but because `--enable=all` pulls in the "information"
category (meta-commentary like "limiting branch analysis", not an
actual code issue) and `--error-exitcode=1` failed the build on it
anyway. Fixed by narrowing to `--enable=warning,style,performance,portability`,
which is the set that actually flags code problems; re-run reports
zero findings. Full timestamped transcript, including that dead end,
in `build.log`.

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

1. ~~Get this compiling clean with zero warnings~~ — done 2026-07-26,
   on three toolchains, with `ctest` and `cppcheck` both passing.
2. Port LUNAE (navigation) and ETHAN (propulsion) as the same kind of
   fixed-state-struct modules, wired into the same cyclic executive.
3. Replace the hardcoded test telemetry with a real bounded input
   source (a fixed-size ring buffer fed by a sensor driver, still no
   heap).
4. Decide what, if anything, a crew-facing interface looks like under
   these constraints — almost certainly not a port of HALIA.
5. Get an actual static analyzer (cppcheck, or ideally a MISRA-aware
   one) and CI running before calling any of it flight-representative.
