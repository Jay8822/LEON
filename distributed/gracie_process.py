# distributed/gracie_process.py
# Added 2026-07-27 — Jay Pratt + AI (Claude, Anthropic).
"""GRACIE, running as its own OS process, publishing health status over a
TCP socket to a separately-running EDEN process.

Start distributed/eden_process.py FIRST (it listens; this connects).
Then, from the repo root:

    python -m distributed.gracie_process

Uses the real agents.gracie.GracieAgent unmodified — only the bus object
is different from the single-process app (see distributed/socket_bus.py).
"""

import socket
import time

from agents.gracie import GracieAgent
from core.schemas import TelemetryPacket
from distributed.socket_bus import SocketBus

HOST = "127.0.0.1"
PORT = 8765

# Fixed, deterministic sequence — same rationale as the C++ demo's test
# telemetry (see "AI Stack C++ Test Build/README.md"): this is a
# demonstrator whose job is to reliably prove the fault-escalation
# crossing every run, not a simulation, so it doesn't depend on random
# telemetry happening to hit both thresholds together.
#
# To be explicit, since a reviewer running this could otherwise mistake
# reproducible input for a rigged result: this is scripted test input,
# not staged output. The sequence is fixed on purpose so the demo
# reliably and reproducibly walks NOMINAL -> WARNING -> FAULT, with
# the fault latching, on every run. What happens after each reading —
# GracieAgent's health evaluation, the latch, EDEN's SAFE_MODE
# escalation over the socket — is the real, unmodified agent logic
# reacting live to whatever this array contains, not a scripted or
# faked response.
TELEMETRY_SEQUENCE = [
    (30.0, 10.0),  # NOMINAL
    (52.0, 15.0),  # WARNING
    (56.0, 45.0),  # FAULT — this is the one that must cross to EDEN
    (30.0, 10.0),  # telemetry recovers; FAULT stays latched
]


def connect(host, port, retries=10, delay=1.0):
    for attempt in range(1, retries + 1):
        try:
            return socket.create_connection((host, port))
        except ConnectionRefusedError:
            print(f"EDEN not up yet (attempt {attempt}/{retries}), retrying in {delay}s...")
            time.sleep(delay)
    raise ConnectionRefusedError(f"Could not connect to EDEN at {host}:{port} after {retries} attempts")


def main():
    print(f"Connecting to EDEN at {HOST}:{PORT}...")
    sock = connect(HOST, PORT)
    print("Connected.")

    bus = SocketBus("gracie_process", sock=sock)
    gracie = GracieAgent(bus)
    bus.logger.info("Connected to EDEN process.")

    for temp_c, radiation in TELEMETRY_SEQUENCE:
        telemetry = TelemetryPacket(
            timestamp=int(time.time()),
            temp_c=temp_c,
            radiation=radiation,
            thrust_demand=0.0,
            nav_state="CRUISE",
            system_health="NOMINAL",
            source="GRACIE_PROCESS",
        )
        gracie.process_telemetry(telemetry)
        print(f"GRACIE: temp={temp_c} rad={radiation} -> {gracie.health_state} (sent to EDEN)")
        time.sleep(1)

    print("GRACIE process done, closing connection.")
    bus.logger.info("Telemetry sequence complete, closing connection to EDEN.")
    sock.close()


if __name__ == "__main__":
    main()
