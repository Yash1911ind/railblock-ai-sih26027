import pandas as pd

from railblock.data import load_demo_data
from railblock.digital_twin import (
    SECTION_STATUSES,
    build_network_figure,
    build_section_states,
    get_section_detail,
    section_risk_level,
    section_status,
)
from railblock.optimizer import optimize_blocks


def _plan_row(**overrides):
    base = {
        "request_id": "MR-X",
        "section_id": "SEC-A",
        "department": "Engineering",
        "status": "Deferred",
        "start_min": None,
        "end_min": None,
        "disruption": 0,
    }
    base.update(overrides)
    return base


def test_network_data_generation_covers_every_known_section():
    data = load_demo_data()
    result = optimize_blocks(data["requests"], data["trains"], data["windows"])
    states = build_section_states(result.plan, result.conflicts, data["assets"], data["trains"], data["windows"])
    expected_sections = set(data["assets"].section_id) | set(data["trains"].section_id) | set(data["windows"].section_id)
    assert {s["section_id"] for s in states} == expected_sections
    for state in states:
        assert state["status"] in SECTION_STATUSES or state["status"] == "AVAILABLE"


def test_section_status_available_when_clear():
    plan = pd.DataFrame([_plan_row(status="Deferred")])
    trains = pd.DataFrame(columns=["train_id", "section_id", "start_min", "end_min"])
    assert section_status("SEC-A", plan, [], trains) == "AVAILABLE"


def test_section_status_maintenance_when_scheduled_block_present():
    plan = pd.DataFrame([_plan_row(status="Scheduled", start_min=60, end_min=120)])
    trains = pd.DataFrame(columns=["train_id", "section_id", "start_min", "end_min"])
    assert section_status("SEC-A", plan, [], trains) == "MAINTENANCE"


def test_section_status_conflict_outranks_maintenance():
    plan = pd.DataFrame([_plan_row(status="Scheduled", start_min=60, end_min=120)])
    trains = pd.DataFrame(columns=["train_id", "section_id", "start_min", "end_min"])
    conflicts = [{"type": "Train", "item": "MR-X", "detail": "Conflicts with protected TR-999"}]
    assert section_status("SEC-A", plan, conflicts, trains) == "CONFLICT"


def test_section_status_restricted_from_synthetic_restriction_train():
    plan = pd.DataFrame([_plan_row(status="Deferred")])
    trains = pd.DataFrame(
        [{"train_id": "RESTRICTION-1", "section_id": "SEC-A", "start_min": 60, "end_min": 180}]
    )
    assert section_status("SEC-A", plan, [], trains) == "RESTRICTED"


def test_section_risk_level_uses_the_existing_risk_engine_and_takes_the_max():
    assets = pd.DataFrame(
        [
            {"asset_id": "A-1", "section_id": "SEC-A", "condition_score": 95, "last_maintenance_days": 5},
            {"asset_id": "A-2", "section_id": "SEC-A", "condition_score": 10, "last_maintenance_days": 400},
        ]
    )
    assert section_risk_level("SEC-A", assets) == "CRITICAL"


def test_section_risk_level_is_na_with_no_assets():
    assets = pd.DataFrame(columns=["asset_id", "section_id", "condition_score", "last_maintenance_days"])
    assert section_risk_level("SEC-A", assets) == "N/A"


def test_block_status_split_between_scheduled_and_deferred():
    data = load_demo_data()
    result = optimize_blocks(data["requests"], data["trains"], data["windows"])
    states = build_section_states(result.plan, result.conflicts, data["assets"], data["trains"], data["windows"])
    sec_c = get_section_detail(states, "SEC-C")
    assert sec_c is not None
    total = len(sec_c["scheduled_blocks"]) + len(sec_c["deferred_requests"])
    expected = len(result.plan[result.plan.section_id == "SEC-C"])
    assert total == expected


def test_train_representation_never_claims_a_real_position():
    data = load_demo_data()
    result = optimize_blocks(data["requests"], data["trains"], data["windows"])
    states = build_section_states(result.plan, result.conflicts, data["assets"], data["trains"], data["windows"])
    sec_a = get_section_detail(states, "SEC-A")
    assert sec_a["trains"], "SEC-A should have trains in the demo dataset"
    for train in sec_a["trains"]:
        assert train["position_label"] == "Scheduled position (simulation)"
        assert "train_id" in train and "start_min" in train and "end_min" in train


def test_missing_data_does_not_crash():
    empty_plan = pd.DataFrame(columns=["request_id", "section_id", "status", "start_min", "end_min", "disruption"])
    empty_assets = pd.DataFrame(columns=["asset_id", "section_id", "condition_score", "last_maintenance_days"])
    empty_trains = pd.DataFrame(columns=["train_id", "section_id", "start_min", "end_min", "importance", "can_delay"])
    empty_windows = pd.DataFrame(columns=["window_id", "section_id", "start_min", "end_min"])
    states = build_section_states(empty_plan, [], empty_assets, empty_trains, empty_windows)
    assert states == []
    assert get_section_detail(states, "SEC-A") is None


def test_get_section_detail_returns_none_for_unknown_section():
    data = load_demo_data()
    result = optimize_blocks(data["requests"], data["trains"], data["windows"])
    states = build_section_states(result.plan, result.conflicts, data["assets"], data["trains"], data["windows"])
    assert get_section_detail(states, "SEC-DOES-NOT-EXIST") is None


def test_build_network_figure_does_not_crash_and_has_a_trace_per_section():
    data = load_demo_data()
    result = optimize_blocks(data["requests"], data["trains"], data["windows"])
    states = build_section_states(result.plan, result.conflicts, data["assets"], data["trains"], data["windows"])
    figure = build_network_figure(states)
    # one connecting line trace + one marker trace per section
    assert len(figure.data) == 1 + len(states)


def test_build_network_figure_handles_empty_states():
    figure = build_network_figure([])
    assert len(figure.data) == 1
