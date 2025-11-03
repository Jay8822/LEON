# core/schemas.py

from dataclasses import dataclass
from typing import Literal, Optional

@dataclass
class TelemetryPacket:
    timestamp: int
    temp_c: float
    radiation: float
    thrust_demand: float
    nav_state: str
    system_health: Literal["NOMINAL", "WARNING", "FAULT"]
    source: str

@dataclass
class CommandPacket:
    command: Literal["SAFE_MODE", "PROPULSION_SET", "NAV_ADJUST"]
    mode: Optional[str]  # e.g. "NTP", "NEP", "PLASMA"
    reason: str
