"""Data models for IP host monitoring (wake/sleep) events."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class IpTarget:
    """One IP/hostname to actively monitor with periodic pings."""

    ip: str
    hostname: Optional[str] = None


@dataclass
class IpStatusEvent:
    """One wake (down->up) or sleep (up->down) transition for a monitored IP."""

    timestamp: str = field(default_factory=_now_iso)
    ip: str = ""
    hostname: Optional[str] = None
    status: str = ""  # "up" | "down"
    rtt_ms: Optional[float] = None
    source: str = "active"  # "active" (ping poll) | "passive" (inferred from RF capture)
