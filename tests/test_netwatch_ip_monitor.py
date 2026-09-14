from netwatch.ip_monitor import IpMonitor
from netwatch.models import IpTarget


def test_first_check_establishes_status_and_emits_event():
    events = []
    monitor = IpMonitor([IpTarget(ip="10.0.0.1", hostname="router")],
                         ping_fn=lambda ip, timeout: 1.2, on_event=events.append)
    result = monitor.poll_once()
    assert len(result) == 1
    assert result[0].ip == "10.0.0.1"
    assert result[0].status == "up"
    assert result[0].rtt_ms == 1.2
    assert events == result


def test_first_check_down_emits_down_event():
    monitor = IpMonitor([IpTarget(ip="10.0.0.9")], ping_fn=lambda ip, timeout: None)
    events = monitor.poll_once()
    assert len(events) == 1
    assert events[0].status == "down"


def test_transition_from_up_to_down_emits_sleep_event():
    replies = iter([1.0, None])
    monitor = IpMonitor([IpTarget(ip="10.0.0.1")], ping_fn=lambda ip, timeout: next(replies))
    monitor.poll_once()
    events = monitor.poll_once()
    assert len(events) == 1
    assert events[0].status == "down"


def test_transition_from_down_to_up_emits_wake_event():
    replies = iter([None, 3.5])
    monitor = IpMonitor([IpTarget(ip="10.0.0.1")], ping_fn=lambda ip, timeout: next(replies))
    monitor.poll_once()
    events = monitor.poll_once()
    assert len(events) == 1
    assert events[0].status == "up"
    assert events[0].rtt_ms == 3.5


def test_no_change_emits_no_event():
    monitor = IpMonitor([IpTarget(ip="10.0.0.1")], ping_fn=lambda ip, timeout: 1.0)
    monitor.poll_once()
    events = monitor.poll_once()
    assert events == []


def test_snapshot_reports_current_state_per_target():
    monitor = IpMonitor(
        [IpTarget(ip="10.0.0.1", hostname="router"), IpTarget(ip="10.0.0.2", hostname="nas")],
        ping_fn=lambda ip, timeout: 5.0 if ip == "10.0.0.1" else None,
    )
    monitor.poll_once()
    snap = {row["ip"]: row for row in monitor.snapshot()}

    assert snap["10.0.0.1"]["hostname"] == "router"
    assert snap["10.0.0.1"]["status"] == "up"
    assert snap["10.0.0.1"]["rtt_ms"] == 5.0
    assert snap["10.0.0.1"]["since"] is not None

    assert snap["10.0.0.2"]["status"] == "down"
    assert snap["10.0.0.2"]["rtt_ms"] is None
