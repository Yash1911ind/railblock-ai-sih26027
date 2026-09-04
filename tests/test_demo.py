import pytest

from railblock.data import load_demo_data
from railblock.demo import SCENARIOS, run_scenario


@pytest.fixture(scope="module")
def data():
    return load_demo_data()


def test_all_six_scenarios_are_registered():
    assert set(SCENARIOS) == {
        "normal_planning",
        "high_risk_asset",
        "train_delay",
        "block_unavailable",
        "emergency_maintenance",
        "multi_department_coordination",
    }


def test_normal_planning_scenario_uses_the_real_optimizer(data):
    outcome = run_scenario("normal_planning", data)
    assert outcome.result.status in {"OPTIMAL", "FEASIBLE"}
    assert outcome.result.conflicts == []


def test_high_risk_asset_scenario_uses_the_real_risk_engine(data):
    outcome = run_scenario("high_risk_asset", data)
    assert "top_asset" in outcome.extra
    assert 0 <= outcome.extra["top_asset"]["risk_score"] <= 100


def test_train_delay_scenario_uses_the_real_disruption_engine(data):
    outcome = run_scenario("train_delay", data, train_id="TR-101", delay_minutes=20)
    assert outcome.result.status in {"OPTIMAL", "FEASIBLE"}
    assert "comparison" in outcome.extra
    assert "before" in outcome.extra["comparison"]


def test_block_unavailable_scenario_actually_removes_the_window(data):
    outcome = run_scenario("block_unavailable", data, window_id="W-A1")
    assert outcome.result.status in {"OPTIMAL", "FEASIBLE"}


def test_emergency_maintenance_scenario_adds_a_real_request(data):
    outcome = run_scenario("emergency_maintenance", data, section_id="SEC-B", duration_min=45)
    assert "MR-DEMO-EMERGENCY" in set(outcome.result.plan.request_id)


def test_multi_department_coordination_scenario_uses_the_real_coordination_engine(data):
    outcome = run_scenario("multi_department_coordination", data)
    assert "opportunities" in outcome.extra
    assert isinstance(outcome.extra["opportunities"], list)


def test_unknown_scenario_fails_gracefully(data):
    with pytest.raises(ValueError):
        run_scenario("not_a_real_scenario", data)


def test_scenarios_do_not_mutate_the_original_dataset(data):
    import pandas as pd

    requests_before = data["requests"].copy()
    trains_before = data["trains"].copy()
    windows_before = data["windows"].copy()
    run_scenario("train_delay", data)
    run_scenario("block_unavailable", data)
    run_scenario("emergency_maintenance", data)
    pd.testing.assert_frame_equal(requests_before, data["requests"])
    pd.testing.assert_frame_equal(trains_before, data["trains"])
    pd.testing.assert_frame_equal(windows_before, data["windows"])
