# agents/chester.py
# Added 2026-10-25 — Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""CHESTER — SPEC.md's "ship-wide watcher, no authority" section. A
PA for the agents, not a manager: he watches, remembers, keeps timers,
and tells the relevant agent, but the owning agent still makes every
decision. Built against the plan agreed in "Ccode update.txt" history
(Job 4 of that round, then Part 3 of the follow-up round that also
extended GRACIE's announcements and gave the orchestrator a real
ping_agent() method).

Interpretive calls made, agreed with Jay before building:

1. CHESTER keeps his OWN, independent record of leash timing from
   what GRACIE announces on "chester/watch" -- he does not replace or
   duplicate GRACIE's own internal tracking (agents/gracie.py's
   _ChannelState), which stays exactly as it is. Whether leash timing
   ever actually moves out of GRACIE and into CHESTER is a separate,
   later decision -- not made here, and would be a GRACIE change.
2. on_watch() handles whatever "kind" of announcement arrives
   generically -- it doesn't hardcode to "leash_settled" the way the
   very first version of this idea might have. With GRACIE now
   announcing "jump", "warning_entered", "warning_left" and
   "leash_settled" (agents/gracie.py, module docstring point 10),
   this is tested against all four, against a REAL GracieAgent, not
   just synthetic payloads.
3. The ignored-agent check uses the real EscalationOrchestrator.
   ping_agent() (added alongside this), not a stub -- CHESTER still
   doesn't ping the agent himself (he has no bus-level "are you alive"
   mechanism of his own); `responded` is supplied by the caller, same
   as the orchestrator's own method takes it from CHESTER rather than
   performing the ping itself. See ping_agent()'s own docstring in
   agents/escalation_orchestrator.py for why.
4. CHESTER can answer a heartbeat ping if one ever arrives
   (on_heartbeat_ping()) -- but the actual system-wide heartbeat
   mechanism (who pings whom, how often, what happens if nobody
   answers) doesn't exist anywhere in this codebase yet, for any
   component. Building that is separate, future, cross-cutting work,
   not part of building CHESTER himself.
5. Ghost memory: a "layer" is everything CHESTER received in one
   refresh window (refresh_period_seconds -- a rule-book setting, no
   default, "10 minutes is the intended starting value" per SPEC.md,
   not claimed as a real number yet). max_layers (also no default) is
   when the storage-full rule kicks in: the OLDEST layer is dropped
   from ghost memory once there are too many -- never from the
   permanent log, which is written to immediately on receipt and
   never edited or deleted, so "only once safely logged" is always
   already true by the time a layer would be dropped. A human is
   flagged one layer before that point (max_layers - 1), not only at
   the moment of eviction. End-of-mission/day tidying
   (tidy_ghost_memory()) removes whatever an injected `is_irrelevant`
   predicate (a rule-book-driven filter, no default -- "irrelevant"
   is defined by the rule book, not by CHESTER) says doesn't matter
   any more, from the CURRENT ghost-memory layers only -- the
   permanent log is never touched by tidying either.

Light-flag reminders: an item "opens" when a "warning_entered"
announcement arrives, and "closes" when a matching "warning_left" or
"leash_settled" arrives for the same (agent, channel). Each light_flag_
tick() call re-flags every still-open item -- the repetition is the
point (same "not an active alert, just a recurring reminder" idea as
EscalationOrchestrator's own light_flag_tick()), not something to
suppress on repeat calls.

No invented numbers: refresh_period_seconds, max_layers and
is_irrelevant are all required constructor arguments, no defaults.
"""

from collections import deque
from typing import Callable, Deque, Dict, List, Optional, Tuple

from core.bus import EventBus
from core.logger import setup_agent_logger

# Kinds that close an open "entered WARNING" item.
_CLOSING_KINDS = {"warning_left", "leash_settled"}


class ChesterAgent:
    def __init__(
        self,
        bus: EventBus,
        orchestrator,
        refresh_period_seconds: float,
        max_layers: int,
        is_irrelevant: Callable[[dict], bool],
    ):
        self.logger = setup_agent_logger("chester")
        self.bus = bus
        self.orchestrator = orchestrator
        self.refresh_period_seconds = refresh_period_seconds
        self.max_layers = max_layers
        self.is_irrelevant = is_irrelevant

        self._permanent_log: List[dict] = []  # raw log -- never edited, never deleted
        self._layers: Deque[List[dict]] = deque()
        self._current_layer: List[dict] = []
        self._layer_started_at: Optional[float] = None
        self._open_items: Dict[Tuple[str, str], dict] = {}  # (agent, channel) -> entry

        self.bus.subscribe("chester/watch", self.on_watch)
        self.bus.subscribe("chester/heartbeat_ping", self.on_heartbeat_ping)
        self._layers.append(self._current_layer)

    # --- watching -------------------------------------------------------
    def on_watch(self, payload: dict):
        """Generic -- handles whatever "kind" of announcement arrives,
        per module docstring point 2."""
        entry = dict(payload)
        self._permanent_log.append(entry)  # logs as he goes, immediately
        self._current_layer.append(entry)
        self.logger.info(
            f"watch: kind={entry.get('kind')} agent={entry.get('agent')} channel={entry.get('channel')}"
        )

        key = (entry.get("agent"), entry.get("channel"))
        kind = entry.get("kind")
        if kind == "warning_entered":
            self._open_items[key] = entry
        elif kind in _CLOSING_KINDS:
            self._open_items.pop(key, None)

    def open_items(self) -> List[dict]:
        return list(self._open_items.values())

    # --- the ticking clock: ghost memory refresh + light-flag reminders -
    def tick(self, now_seconds: float):
        """Call once per self-check cycle. Refreshes ghost memory's
        current layer if the refresh period has elapsed, then re-flags
        every still-open item."""
        if self._layer_started_at is None:
            self._layer_started_at = now_seconds
        elif now_seconds - self._layer_started_at >= self.refresh_period_seconds:
            self._refresh_layer()
            self._layer_started_at = now_seconds

        for (agent, channel), entry in self._open_items.items():
            self.logger.info(
                f"light flag (recurring, not an active alert): {agent}/{channel} still open "
                f"since kind={entry.get('kind')} at t={entry.get('timestamp')}"
            )

    def _refresh_layer(self):
        self._current_layer = []
        self._layers.append(self._current_layer)
        if len(self._layers) > self.max_layers:
            dropped = self._layers.popleft()
            self.logger.info(
                f"storage-full rule: dropped the oldest ghost layer ({len(dropped)} entries) -- "
                f"already safely in the permanent log"
            )
        elif len(self._layers) == self.max_layers:
            self.logger.warning(
                f"ghost memory nearing full ({len(self._layers)}/{self.max_layers} layers) -- flagged for a human"
            )

    def ghost_memory_layers(self) -> List[List[dict]]:
        return list(self._layers)

    def permanent_log(self) -> List[dict]:
        return list(self._permanent_log)

    # --- end-of-mission/day tidy -----------------------------------------
    def tidy_ghost_memory(self):
        """Removes whatever `is_irrelevant` says doesn't matter any
        more, from the current ghost-memory layers only. The
        permanent log (already written) is never touched."""
        removed = 0
        for layer in self._layers:
            kept = [e for e in layer if not self.is_irrelevant(e)]
            removed += len(layer) - len(kept)
            layer[:] = kept
        self.logger.info(f"end-of-mission tidy: removed {removed} irrelevant entries from ghost memory")

    # --- ignored-agent check (via the orchestrator) -----------------------
    def report_ignored_agent(self, agent: str, responded: bool):
        """An agent ignored CHESTER -- notify the orchestrator, which
        pings that agent (module docstring point 3) to confirm it's
        active, and add a flag to CHESTER's own log either way."""
        result = self.orchestrator.ping_agent(agent, responded)
        flag = {"kind": "ignored_agent_ping", "agent": agent, "outcome": result.outcome}
        self._permanent_log.append(flag)
        self._current_layer.append(flag)
        self.logger.info(f"ignored-agent flag for {agent}: orchestrator says {result.outcome}")
        return result

    # --- heartbeat --------------------------------------------------------
    def on_heartbeat_ping(self, payload: dict):
        """Answers a ping if one ever arrives. The mechanism that
        sends pings in the first place doesn't exist yet (module
        docstring point 4)."""
        self.logger.info("heartbeat ping received -- answering")
        self.bus.publish("chester/heartbeat_response", {"status": "alive"})
