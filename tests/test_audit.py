from railblock.audit import AUDIT_ACTIONS, format_event, record_event


def test_record_event_appends_and_returns_the_event():
    log = []
    event = record_event(log, "AI Recommendation Approved", "MR-001", "Controller approved HIGH priority")
    assert log == [event]
    assert event["action"] == "AI Recommendation Approved"
    assert event["entity"] == "MR-001"
    assert event["reason"] == "Controller approved HIGH priority"
    assert "timestamp" in event


def test_record_event_preserves_order_across_multiple_calls():
    log = []
    record_event(log, "Schedule Generated", "Plan", "Initial CP-SAT solve")
    record_event(log, "Disruption Introduced", "TR-101", "Simulated 20 min delay")
    assert len(log) == 2
    assert log[0]["action"] == "Schedule Generated"
    assert log[1]["action"] == "Disruption Introduced"


def test_format_event_includes_all_fields():
    log = []
    event = record_event(log, "Re-plan Generated", "MR-002", "Applied after disruption")
    formatted = format_event(event)
    assert event["timestamp"] in formatted
    assert "Re-plan Generated" in formatted
    assert "MR-002" in formatted
    assert "Applied after disruption" in formatted


def test_audit_actions_cover_the_required_event_types():
    required = {
        "AI Recommendation Generated",
        "AI Recommendation Approved",
        "AI Recommendation Rejected",
        "Schedule Generated",
        "Simulation Executed",
        "Disruption Introduced",
        "Re-plan Generated",
    }
    assert required.issubset(set(AUDIT_ACTIONS))


def test_record_event_does_not_touch_unrelated_log_entries():
    log = [{"timestamp": "00:00:00", "action": "existing", "entity": "X", "reason": "prior"}]
    record_event(log, "Schedule Modified", "MR-003", "Manual override")
    assert log[0]["action"] == "existing"
    assert len(log) == 2
