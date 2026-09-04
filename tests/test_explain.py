import pandas as pd
import pytest

from railblock.data import load_demo_data
from railblock.explain import explain_all, explain_recommendation
from railblock.optimizer import PlanningResult, optimize_blocks


def _minimal_plan_row(**overrides):
    base = {
        "request_id": "MR-X",
        "asset_id": "A-X",
        "work_type": "Test work",
        "section_id": "SEC-A",
        "department": "Engineering",
        "duration_min": 60,
        "priority": 3,
        "earliest_start": 60,
        "latest_end": 420,
        "crew_id": "CREW-E1",
        "start_min": None,
        "end_min": None,
        "disruption": 0,
        "window_id": None,
        "status": "Deferred",
    }
    base.update(overrides)
    return base


@pytest.fixture(scope="module")
def demo_result():
    data = load_demo_data()
    return data, optimize_blocks(data["requests"], data["trains"], data["windows"])


def test_options_by_request_is_populated(demo_result):
    _, result = demo_result
    assert result.options_by_request is not None
    assert set(result.options_by_request) == set(result.plan.request_id)


def test_scheduled_explanation_is_grounded_in_actual_values(demo_result):
    data, result = demo_result
    scheduled_ids = result.plan[result.plan.status == "Scheduled"].request_id.tolist()
    assert scheduled_ids, "demo data should schedule at least one request"
    request_id = scheduled_ids[0]
    block = result.plan[result.plan.request_id == request_id].iloc[0]

    explanation = explain_recommendation(request_id, result, data["assets"])
    assert explanation["status"] == "Scheduled"
    assert explanation["reasons"]
    joined = " ".join(explanation["reasons"])
    assert str(int(block.disruption)) in joined
    assert request_id in explanation["headline"]


def test_deferred_explanation_is_grounded_in_actual_values(demo_result):
    _, result = demo_result
    deferred_ids = result.plan[result.plan.status == "Deferred"].request_id.tolist()
    if not deferred_ids:
        pytest.skip("demo data did not defer any request in this run")
    explanation = explain_recommendation(deferred_ids[0], result, None)
    assert explanation["status"] == "Deferred"
    assert explanation["reasons"]


def test_unknown_request_id_raises(demo_result):
    _, result = demo_result
    with pytest.raises(ValueError):
        explain_recommendation("MR-DOES-NOT-EXIST", result)


def test_explanation_survives_missing_asset_table(demo_result):
    _, result = demo_result
    request_id = result.plan.request_id.iloc[0]
    explanation = explain_recommendation(request_id, result, assets_df=None)
    assert explanation["reasons"]


def test_explain_all_covers_every_request(demo_result):
    data, result = demo_result
    explanations = explain_all(result, data["assets"])
    assert set(explanations) == set(result.plan.request_id)


def test_explanation_does_not_mutate_plan(demo_result):
    _, result = demo_result
    before = result.plan.copy()
    explain_recommendation(result.plan.request_id.iloc[0], result)
    pd.testing.assert_frame_equal(before, result.plan)


def test_deferred_with_no_feasible_options_explains_infeasibility():
    plan = pd.DataFrame([_minimal_plan_row()])
    result = PlanningResult(
        plan, conflicts=[], metrics={}, status="OPTIMAL", solve_seconds=0.01,
        options_by_request={"MR-X": []},
    )
    explanation = explain_recommendation("MR-X", result)
    assert explanation["status"] == "Deferred"
    assert "no feasible option" in explanation["reasons"][0]


def test_deferred_with_rejected_options_explains_tradeoff():
    plan = pd.DataFrame([_minimal_plan_row()])
    options = [{"start": 60, "end": 120, "disruption": 5, "window_id": "W-A1"}]
    result = PlanningResult(
        plan, conflicts=[], metrics={}, status="OPTIMAL", solve_seconds=0.01,
        options_by_request={"MR-X": options},
    )
    explanation = explain_recommendation("MR-X", result)
    assert "1 candidate start time" in explanation["reasons"][0]


def test_scheduled_explanation_flags_department_coordination():
    plan = pd.DataFrame(
        [
            _minimal_plan_row(
                request_id="MR-A", department="Engineering", section_id="SEC-A",
                window_id="W-A1", status="Scheduled", start_min=60, end_min=120, disruption=5,
            ),
            _minimal_plan_row(
                request_id="MR-B", department="S&T", section_id="SEC-A",
                window_id="W-A1", status="Scheduled", start_min=150, end_min=200, disruption=0,
            ),
        ]
    )
    result = PlanningResult(
        plan, conflicts=[], metrics={}, status="OPTIMAL", solve_seconds=0.01,
        options_by_request={
            "MR-A": [{"start": 60, "end": 120, "disruption": 5, "window_id": "W-A1"}],
            "MR-B": [{"start": 150, "end": 200, "disruption": 0, "window_id": "W-A1"}],
        },
    )
    explanation = explain_recommendation("MR-A", result)
    assert any("compatible task" in reason for reason in explanation["reasons"])
