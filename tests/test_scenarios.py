from unittest.mock import patch

import pandas as pd
import pytest

from railblock.data import load_demo_data
from railblock.optimizer import optimize_blocks
from railblock.scenarios import run_what_if_scenario


def test_scenario_does_not_modify_original_plan():
    data = load_demo_data()
    current = optimize_blocks(data["requests"], data["trains"], data["windows"])
    current_plan_before = current.plan.copy()
    requests_before = data["requests"].copy()
    trains_before = data["trains"].copy()
    windows_before = data["windows"].copy()

    run_what_if_scenario(
        data["requests"], data["trains"], data["windows"],
        {"type": "TRAIN_DELAY", "train_id": "TR-101", "delay_minutes": 20},
        current_result=current,
    )

    pd.testing.assert_frame_equal(current_plan_before, current.plan)
    pd.testing.assert_frame_equal(requests_before, data["requests"])
    pd.testing.assert_frame_equal(trains_before, data["trains"])
    pd.testing.assert_frame_equal(windows_before, data["windows"])


def test_optimizer_runs_on_the_simulated_state():
    data = load_demo_data()
    current = optimize_blocks(data["requests"], data["trains"], data["windows"])

    simulation = run_what_if_scenario(
        data["requests"], data["trains"], data["windows"],
        {"type": "BLOCK_UNAVAILABLE", "window_id": "W-A1"},
        current_result=current,
    )

    assert "W-A1" not in set(simulation.simulated_windows.window_id)
    assert simulation.simulated_result.status in {"OPTIMAL", "FEASIBLE"}
    assert simulation.simulated_result.conflicts == []


def test_before_after_comparison_uses_actual_values():
    data = load_demo_data()
    current = optimize_blocks(data["requests"], data["trains"], data["windows"])

    simulation = run_what_if_scenario(
        data["requests"], data["trains"], data["windows"],
        {"type": "TRAIN_DELAY", "train_id": "TR-101", "delay_minutes": 20},
        current_result=current,
    )

    expected_before_scheduled = len(current.plan[current.plan.status == "Scheduled"])
    expected_after_scheduled = len(simulation.simulated_result.plan[simulation.simulated_result.plan.status == "Scheduled"])
    assert simulation.comparison["before"]["scheduled_requests"] == expected_before_scheduled
    assert simulation.comparison["after"]["scheduled_requests"] == expected_after_scheduled
    assert simulation.current_result is current


def test_invalid_scenario_type_fails_gracefully():
    data = load_demo_data()
    with pytest.raises(ValueError):
        run_what_if_scenario(
            data["requests"], data["trains"], data["windows"],
            {"type": "NOT_A_REAL_SCENARIO"},
        )


def test_invalid_scenario_parameters_fail_gracefully():
    data = load_demo_data()
    with pytest.raises(ValueError):
        run_what_if_scenario(
            data["requests"], data["trains"], data["windows"],
            {"type": "TRAIN_DELAY", "train_id": "TR-DOES-NOT-EXIST", "delay_minutes": 10},
        )


def test_multiple_disruptions_scenario_e_is_supported():
    data = load_demo_data()
    simulation = run_what_if_scenario(
        data["requests"], data["trains"], data["windows"],
        [
            {"type": "TRAIN_DELAY", "train_id": "TR-101", "delay_minutes": 20},
            {"type": "DURATION_INCREASE", "request_id": "MR-002", "additional_minutes": 30},
        ],
    )
    assert len(simulation.scenarios) == 2
    assert simulation.simulated_result.status in {"OPTIMAL", "FEASIBLE"}


def test_one_optimization_call_when_baseline_is_supplied():
    data = load_demo_data()
    current = optimize_blocks(data["requests"], data["trains"], data["windows"])

    with patch("railblock.disruptions.optimize_blocks", wraps=optimize_blocks) as spy:
        run_what_if_scenario(
            data["requests"], data["trains"], data["windows"],
            {"type": "TRAIN_DELAY", "train_id": "TR-101", "delay_minutes": 20},
            current_result=current,
        )
        assert spy.call_count == 1


def test_two_optimization_calls_when_no_baseline_supplied():
    data = load_demo_data()
    with patch("railblock.disruptions.optimize_blocks", wraps=optimize_blocks) as spy:
        run_what_if_scenario(
            data["requests"], data["trains"], data["windows"],
            {"type": "TRAIN_DELAY", "train_id": "TR-101", "delay_minutes": 20},
        )
        assert spy.call_count == 2
