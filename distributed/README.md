# Standalone-process demonstrator

Proves genuine module independence: GRACIE and EDEN, running as two
separate OS processes, communicating over a real inter-process
transport — not two objects sharing one in-memory bus inside a single
Python process, which is what `main.py` does.

## Why this exists

The rest of this repo's Python agents all share `core.bus.EventBus`
inside one process. That's honest for a ground-simulation prototype,
but it doesn't prove the agents are actually independent modules —
they could be quietly relying on shared memory, import order, or
process-local state without anyone noticing. Running two of them as
genuinely separate processes, talking only over a socket, is a real
test of that independence: if it works, the modules truly don't share
anything except an agreed-on message format.

## The transport: plain TCP sockets, on purpose

`socket_bus.py` is a raw TCP socket carrying newline-delimited JSON.
That is **not** what a real distributed build of this system would
use — it has no discovery, no reconnection, no multi-subscriber
fan-out, and it's hardcoded to one connection between exactly two
processes. The real choices for that:

- **DDS** (Data Distribution Service) — the actual aerospace-standard
  pub/sub middleware for exactly this kind of system. Discovery, QoS
  policies, redundancy, multi-subscriber fan-out built in.
- **ZeroMQ** — a common, lighter-weight choice for ground/prototype
  systems that still want real pub/sub semantics without a full DDS
  implementation.

Plain sockets were used here deliberately instead, because the goal of
this demonstrator is to prove the concept as simply and inspectably as
possible — every byte that crosses the process boundary is visible in
`socket_bus.py` in about 100 lines, with no framework's internals to
take on faith. Pulling in DDS or ZeroMQ here would answer a question
nobody asked yet ("does this scale to N processes with real QoS?")
before answering the one that matters first ("do these two modules
actually work independently at all?").

## What didn't change

`GracieAgent` and `EdenAgent` themselves — zero modifications. Each
process imports the real class from `agents/` and constructs it with
`SocketBus` instead of `core.bus.EventBus`. `SocketBus` implements the
same `subscribe(topic, handler)` / `publish(topic, payload)` signature,
so from the agent's point of view nothing is different — it doesn't
know or care whether its handler is about to be called by a local
function call or by a socket-reading thread on the other end of a
wire. That interface compatibility is the actual point being
demonstrated, more than the FAULT/SAFE_MODE result itself.

## Running it

Requires two terminals, from the repo root.

**Terminal 1 — start EDEN first** (it listens; GRACIE connects to it):

    python -m distributed.eden_process

**Terminal 2 — start GRACIE:**

    python -m distributed.gracie_process

GRACIE runs a fixed, deterministic telemetry sequence (not random —
same reasoning as the C++ demo's fixed test data: this is a
demonstrator that should reliably prove the crossing every run, not a
simulation) ending in a FAULT reading, sends each reading to EDEN over
the socket, and disconnects when done. EDEN prints and logs its
reaction to each one and exits cleanly on disconnect.

## What a clean run looks like

Captured 2026-07-27 (two genuinely separate OS processes; full detail
in `logs/gracie_process.log` and `logs/eden_process.log`):

```
GRACIE: temp=30.0 rad=10.0 -> NOMINAL (sent to EDEN)
GRACIE: temp=52.0 rad=15.0 -> WARNING (sent to EDEN)
GRACIE: temp=56.0 rad=45.0 -> FAULT (sent to EDEN)
GRACIE: temp=30.0 rad=10.0 -> FAULT (sent to EDEN)
GRACIE process done, closing connection.
```
```
EDEN issued command: {'command': 'SAFE_MODE', 'mode': None, 'reason': 'GRACIE_FAULT'}
EDEN status: {'status': 'SAFE_MODE', 'timestamp': 1785171580}
EDEN issued command: {'command': 'SAFE_MODE', 'mode': None, 'reason': 'GRACIE_FAULT'}
EDEN status: {'status': 'SAFE_MODE', 'timestamp': 1785171581}
GRACIE disconnected. EDEN process exiting.
```

SAFE_MODE fires on both post-FAULT cycles, matching GRACIE's FAULT
latch (the 4th reading recovers below threshold, but the FAULT from
the 3rd reading is still latched, so GRACIE keeps reporting FAULT and
EDEN keeps responding — same latch behavior as the single-process app,
now proven to survive a real process boundary).

## What it would take to extend this to ETHAN, LUNAE, HALIA

Not built — reporting only, per scope. Each would need:

- **ETHAN**: straightforward — it already only reacts to
  `cmd/propulsion` and `ethan/command`, no different in shape from
  EDEN here. Would need its own process file subscribing to
  `cmd/propulsion` the way `eden_process.py` subscribes to
  `telemetry/health`.
- **LUNAE**: same shape as ETHAN/GRACIE — subscribes to commands,
  publishes nav updates. No new transport concept needed.
- **HALIA**: the one that actually complicates the picture. It needs a
  `coordinator` object with `get_status()`/`send_command()` — in the
  single-process app that's a real `SystemCoordinator` sharing the
  same bus. Distributed, HALIA's process would need either (a) its own
  local coordinator that itself forwards commands over more sockets to
  wherever ETHAN/GRACIE/LUNAE/EDEN actually live, or (b) an actual
  broker process other agents register with — at which point you're
  no longer extending `SocketBus`'s one-connection-per-pair model, you
  need real pub/sub with multiple subscribers per topic across
  multiple processes. That's exactly the point where DDS/ZeroMQ stop
  being optional and start being the honest choice, rather than
  hand-rolling a broker on top of raw sockets.

The two-process version here deliberately stops short of that: it's
the smallest slice that proves the concept, not a scaffold for the
whole mesh.
