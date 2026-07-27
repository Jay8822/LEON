# distributed/eden_process.py
# Added 2026-07-27 — Jay Pratt + AI (Claude, Anthropic).
"""EDEN, running as its own OS process.

Start this FIRST — it listens on 127.0.0.1:8765 and waits for GRACIE to
connect. Then, in a second terminal, from the repo root:

    python -m distributed.eden_process

...and in the first terminal (or a third):

    python -m distributed.gracie_process

Uses the real agents.eden.EdenAgent unmodified — only the bus object is
different from the single-process app (see distributed/socket_bus.py).
"""

import socket
import threading

from agents.eden import EdenAgent
from distributed.socket_bus import SocketBus, start_reader_thread

HOST = "127.0.0.1"
PORT = 8765


def main():
    bus = SocketBus("eden_process")
    eden = EdenAgent(bus)
    # Mirrors main.py's wiring: on_health_event isn't subscribed inside
    # EdenAgent itself, it's wired externally by whoever owns the bus —
    # same division of responsibility here as in the single-process app.
    bus.subscribe("telemetry/health", eden.on_health_event)
    # Not required for the fault-escalation path itself, just makes the
    # terminal output show EDEN's reaction directly.
    bus.subscribe("cmd/propulsion", lambda p: print(f"EDEN issued command: {p}"))
    bus.subscribe("eden/status_update", lambda p: print(f"EDEN status: {p}"))

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    print(f"EDEN process listening on {HOST}:{PORT}. Waiting for GRACIE to connect...")
    bus.logger.info(f"Listening on {HOST}:{PORT}, waiting for GRACIE process to connect.")

    conn, addr = server.accept()
    print(f"GRACIE connected from {addr}.")
    bus.logger.info(f"GRACIE process connected from {addr}.")

    stop_event = threading.Event()
    start_reader_thread(conn, bus, stop_event)

    stop_event.wait()  # blocks until GRACIE disconnects
    print("GRACIE disconnected. EDEN process exiting.")
    bus.logger.info("GRACIE process disconnected. Exiting.")
    server.close()


if __name__ == "__main__":
    main()
