"""Active IP host monitoring: periodic ping polling with wake/sleep transition logging."""

import re
import subprocess
import threading
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional

from .models import IpStatusEvent, IpTarget

_RTT_RE = re.compile(r"time[=<]([\d.]+)")

PingFn = Callable[[str, float], Optional[float]]


def ping_once(ip: str, timeout: float = 1.0) -> Optional[float]:
    """Send one ICMP echo via the system `ping` binary.

    Returns round-trip time in milliseconds if the host replied, or None if
    it didn't (down, unreachable, or timed out).
    """
    wait_secs = max(1, int(round(timeout)))
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(wait_secs), ip],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            timeout=timeout + 2,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    match = _RTT_RE.search(result.stdout)
    return float(match.group(1)) if match else 0.0


class IpMonitor:
    """Polls a set of IP targets on an interval, tracking up/down status and
    producing an event for every wake (down->up) / sleep (up->down)
    transition -- including the first check, which establishes initial state.

    `ping_fn` is injectable (signature `(ip, timeout) -> rtt_ms | None`) so
    this can be exercised in tests without real ICMP traffic; it defaults to
    the real system `ping` binary.
    """

    def __init__(self, targets: Iterable[IpTarget], interval: float = 30.0,
                 timeout: float = 1.0, ping_fn: PingFn = ping_once,
                 on_event: Optional[Callable[[IpStatusEvent], None]] = None):
        self.targets = list(targets)
        self.interval = interval
        self.timeout = timeout
        self._ping_fn = ping_fn
        self._on_event = on_event
        self._status: Dict[str, dict] = {
            t.ip: {"hostname": t.hostname, "status": "unknown", "since": None,
                   "last_checked": None, "rtt_ms": None}
            for t in self.targets
        }
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def poll_once(self) -> List[IpStatusEvent]:
        """Ping every target once; return transition events for any status change."""
        events: List[IpStatusEvent] = []
        for target in self.targets:
            rtt = self._ping_fn(target.ip, self.timeout)
            new_status = "up" if rtt is not None else "down"
            now = datetime.now(timezone.utc).isoformat()
            with self._lock:
                entry = self._status[target.ip]
                prev_status = entry["status"]
                entry["last_checked"] = now
                entry["rtt_ms"] = rtt
                if new_status != prev_status:
                    entry["status"] = new_status
                    entry["since"] = now
                    events.append(IpStatusEvent(timestamp=now, ip=target.ip, hostname=target.hostname,
                                                 status=new_status, rtt_ms=rtt, source="active"))
        if self._on_event is not None:
            for event in events:
                self._on_event(event)
        return events

    def snapshot(self) -> List[dict]:
        """Current status of every target, sorted by IP."""
        with self._lock:
            return [{"ip": ip, **entry} for ip, entry in sorted(self._status.items())]

    def _run(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self.interval)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.timeout + 2)
