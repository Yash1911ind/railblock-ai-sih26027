import pandas as pd
import pytest

from railblock.data import load_demo_data
from railblock.disruptions import (
    apply_disruption,
    apply_disruptions,
    compare_planning_metrics,
    replan_after_disruption,
)
from railblock.optimizer import optimize_blocks


def test_train_delay_is_applied_correctly():
    data = load_demo_data()
    original_row = data["trains"][data["trains"].train_id == "TR-101"].iloc[0]
    requests, trains, windows = apply_disruption(
        data["requests"], data["trains"], data["windows"],
        {"type": "TRAIN_DELAY", "train_id": "TR-101", "delay_minutes": 20},
    )
    new_row = trains[trains.train_id == "TR-101"].iloc[0]
    assert new_row.start_min == original_row.start_min + 20
    assert new_row.end_min == original_row.end_min + 20
    other_rows = trains[trains.train_id != "TR-101"].reset_index(drop=True)
    original_others = data["trains"][data["trains"].train_id != "TR-101"].reset_index(drop=True)
    pd.testing.assert_frame_equal(other_rows, original_others)


def test_train_delay_requires_known_train():
    data = load_demo_data()
    with pytest.raises(ValueError):
        apply_disruption(
            data["requests"], data["trains"], data["windows"],
            {"type": "TRAIN_DELAY", "train_id": "TR-DOES-NOT-EXIST", "delay_minutes": 10},
        )


def test_block_unavailable_is_applied_correctly():
    data = load_demo_data()
    assert "W-A1" in set(data["windows"].window_id)
    requests, trains, windows = apply_disruption(
        data["requests"], data["trains"], data["windows"],
        {"type": "BLOCK_UNAVAILABLE", "window_id": "W-A1"},
    )
    assert "W-A1" not in set(windows.window_id)
    assert "W-A1" in set(data["windows"].window_id)


def test_emergency_maintenance_can_be_added():
    data = load_demo_data()
    emergency_request = {
        "request_id": "MR-EMERGENCY",
        "asset_id": "A-101",
        "work_type": "Emergency inspection",
        "section_id": "SEC-A",
        "department": "Engineering",
        "duration_min": 45,
        "priority": 5,
        "earliest_start": 0,
        "latest_end": 780,
        "crew_id": "CREW-E1",
    }
    requests, trains, windows = apply_disruption(
        data["requests"], data["trains"], data["windows"],
        {"type": "EMERGENCY_MAINTENANCE", "request": emergency_request},
    )
    assert "MR-EMERGENCY" in set(requests.request_id)
    assert len(requests) == len(data["requests"]) + 1
    assert "MR-EMERGENCY" not in set(data["requests"].request_id)


def test_emergency_maintenance_rejects_incomplete_request():
    data = load_demo_data()
    with pytest.raises(ValueError):
        apply_disruption(
            data["requests"], data["trains"], data["windows"],
            {"type": "EMERGENCY_MAINTENANCE", "request": {"request_id": "MR-BAD"}},
        )


def test_duration_increase_is_applied_correctly():
    data = load_demo_data()
    original_duration = data["requests"][data["requests"].request_id == "MR-001"].duration_min.iloc[0]
    requests, trains, windows = apply_disruption(
        data["requests"], data["trains"], data["windows"],
        {"type": "DURATION_INCREASE", "request_id": "MR-001", "additional_minutes": 30},
    )
    new_duration = requests[requests.request_id == "MR-001"].duration_min.iloc[0]
    assert new_duration == original_duration + 30


def test_temporary_restriction_is_applied_as_synthetic_train():
    data = load_demo_data()
    requests, trains, windows = apply_disruption(
        data["requests"], data["trains"], data["windows"],
        {"type": "TEMPORARY_RESTRICTION", "section_id": "SEC-A", "start_min": 60, "end_min": 180},
    )
    assert len(trains) == len(data["trains"]) + 1
    restriction_rows = trains[trains.train_id.str.startswith("RESTRICTION-")]
    assert len(restriction_rows) == 1
    assert restriction_rows.iloc[0].can_delay == False  # noqa: E712 (explicit bool check)


def test_unknown_disruption_type_fails_gracefully():
    data = load_demo_data()
    with pytest.raises(ValueError):
        apply_disruption(data["requests"], data["trains"], data["windows"], {"type": "NOT_A_REAL_TYPE"})


def test_apply_disruptions_chains_multiple_and_does_not_mutate_original():
    data = load_demo_data()
    requests_before = data["requests"].copy()
    trains_before = data["trains"].copy()
    windows_before = data["windows"].copy()

    requests, trains, windows = apply_disruptions(
        data["requests"], data["trains"], data["windows"],
        [
            {"type": "TRAIN_DELAY", "train_id": "TR-101", "delay_minutes": 15},
            {"type": "BLOCK_UNAVAILABLE", "window_id": "W-A1"},
        ],
    )

    assert trains[trains.train_id == "TR-101"].iloc[0].start_min == trains_before[trains_before.train_id == "TR-101"].iloc[0].start_min + 15
    assert "W-A1" not in set(windows.window_id)

    pd.testing.assert_frame_equal(requests_before, data["requests"])
    pd.testing.assert_frame_equal(trains_before, data["trains"])
    pd.testing.assert_frame_equal(windows_before, data["windows"])


def test_replan_after_disruption_returns_valid_planning_result_and_reuses_baseline():
    data = load_demo_data()
    baseline = optimize_blocks(data["requests"], data["trains"], data["windows"])

    replan = replan_after_disruption(
        data["requests"], data["trains"], data["windows"],
        {"type": "TRAIN_DELAY", "train_id": "TR-101", "delay_minutes": 20},
        baseline_result=baseline,
    )

    assert replan.baseline_result is baseline
    assert replan.result.status in {"OPTIMAL", "FEASIBLE"}
    assert replan.result.conflicts == []
    assert "before" in replan.comparison and "after" in replan.comparison and "improvement" in replan.comparison


def test_replan_after_disruption_computes_its_own_baseline_when_none_given():
    data = load_demo_data()
    replan = replan_after_disruption(
        data["requests"], data["trains"], data["windows"],
        {"type": "BLOCK_UNAVAILABLE", "window_id": "W-A1"},
    )
    assert replan.baseline_result.status in {"OPTIMAL", "FEASIBLE"}
    assert replan.result.status in {"OPTIMAL", "FEASIBLE"}


def test_compare_planning_metrics_uses_actual_values_not_fabricated():
    data = load_demo_data()
    before = optimize_blocks(data["requests"], data["trains"], data["windows"])
    requests, trains, windows = apply_disruption(
        data["requests"], data["trains"], data["windows"],
        {"type": "TRAIN_DELAY", "train_id": "TR-101", "delay_minutes": 20},
    )
    after = optimize_blocks(requests, trains, windows)

    comparison = compare_planning_metrics(
        before, after, before_windows=data["windows"], after_windows=windows
    )
    assert comparison["before"]["scheduled_requests"] == len(before.plan[before.plan.status == "Scheduled"])
    assert comparison["after"]["scheduled_requests"] == len(after.plan[after.plan.status == "Scheduled"])
    assert comparison["improvement"]["conflicts"] == comparison["after"]["conflicts"] - comparison["before"]["conflicts"]
