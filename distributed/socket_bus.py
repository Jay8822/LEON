# distributed/socket_bus.py
# Added 2026-07-27 — Jay Pratt + AI (Claude, Anthropic).
"""Minimal, honest inter-process transport for the standalone-process
demonstrator.

This is NOT what flight software would use. A real distributed build of
this system would use DDS (Data Distribution Service — the actual
aerospace-standard choice for this) or ZeroMQ (a common lighter-weight
choice for ground/prototype systems); both give you discovery, QoS,
reconnection, and multi-subscriber fan-out for free. This module is a
raw TCP socket carrying newline-delimited JSON, kept deliberately small
and inspectable, because the point of this demonstrator is to prove one
thing cleanly: the *same* GracieAgent/EdenAgent classes that share an
in-memory core.bus.EventBus inside one process also work wired to two
separate OS processes, with zero changes to the agent code. Only the
object passed in as `bus` changes.

SocketBus intentionally matches core.bus.EventBus's subscribe()/publish()
signature — that compatibility is what makes the agent classes portable
between "in-process" and "inter-process" without modification.
"""

import json
import threading

from core.logger import setup_agent_logger


class SocketBus:
    def __init__(self, name, sock=None):
        self.subscribers = {}
        self.logger = setup_agent_logger(name)
        # A connected socket to forward outbound publishes over, if this
        # side of the demonstrator sends to a peer (GRACIE does; EDEN,
        # in this two-process demo, only ever receives).
        self._sock = sock

    def subscribe(self, topic, handler):
        handler_name = getattr(handler, "__name__", repr(handler))
        self.logger.info(f"Subscribing to '{topic}' with handler '{handler_name}'")
        self.subscribers.setdefault(topic, []).append(handler)

    def publish(self, topic, payload):
        """Dispatch to local subscribers, and forward to the peer process
        over the socket if one is attached to this bus."""
        self._dispatch_local(topic, payload)
        if self._sock is not None:
            self._send(topic, payload)

    def deliver_remote(self, topic, payload):
        """Called by the socket-reading thread for each message received
        from the peer. Dispatches to local subscribers only — does not
        re-send it, so there's no ping-pong between the two processes."""
        self.logger.info(f"Received '{topic}' from peer: {payload}")
        self._dispatch_local(topic, payload)

    def _dispatch_local(self, topic, payload):
        handlers = self.subscribers.get(topic, [])
        self.logger.info(f"Dispatching '{topic}' to {len(handlers)} local handler(s): {payload}")
        for handler in list(handlers):
            try:
                handler(payload)
            except Exception:
                handler_name = getattr(handler, "__name__", repr(handler))
                self.logger.exception(
                    f"Handler '{handler_name}' raised while processing '{topic}'"
                )

    def _send(self, topic, payload):
        line = json.dumps({"topic": topic, "payload": payload}) + "\n"
        try:
            self._sock.sendall(line.encode("utf-8"))
            self.logger.info(f"Sent '{topic}' to peer process: {payload}")
        except OSError as e:
            self.logger.error(f"Failed to send '{topic}' to peer process: {e}")


def read_loop(sock, bus, stop_event=None):
    """Blocking loop: read newline-delimited JSON messages from `sock`
    and hand each to bus.deliver_remote(). Returns when the peer
    disconnects. Meant to be run in a background thread — see
    start_reader_thread()."""
    buf = b""
    with sock:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                bus.logger.info("Peer process disconnected.")
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError as e:
                    bus.logger.error(f"Malformed message from peer, dropped: {e}")
                    continue
                bus.deliver_remote(msg.get("topic"), msg.get("payload"))
    if stop_event is not None:
        stop_event.set()


def start_reader_thread(sock, bus, stop_event=None):
    thread = threading.Thread(target=read_loop, args=(sock, bus, stop_event), daemon=True)
    thread.start()
    return thread
