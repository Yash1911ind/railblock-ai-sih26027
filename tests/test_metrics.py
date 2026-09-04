import pandas as pd

from railblock.coordination import detect_coordination_opportunities
from railblock.data import load_demo_data
from railblock.metrics import (
    average_delay_impact_minutes,
    compare_metrics,
    compute_all_metrics,
    conflict_count,
    critical_risk_assets_addressed,
    deferred_count,
    estimated_possession_reduction_minutes,
    high_risk_assets_addressed,
    risk_weighted_maintenance_coverage_pct,
    schedule_utilization_pct,
    scheduled_count,
    total_maintenance_duration_minutes,
    train_impact_minutes,
)
from railblock.optimizer import baseline_plan, optimize_blocks
from railblock.risk import assess_assets


def _context():
    data = load_demo_data()
    result = optimize_blocks(data["requests"], data["trains"], data["windows"])
    risk_table = assess_assets(data["assets"])
    opportunities = detect_coordination_opportunities(data["requests"], data["windows"])
    return data, result, risk_table, opportunities


def test_scheduled_and_deferred_counts_match_the_plan():
    data, result, _, _ = _context()
    assert scheduled_count(result.plan) + deferred_count(result.plan) == len(result.plan)
    assert scheduled_count(result.plan) == result.metrics["scheduled_requests"]


def test_conflict_count_matches_validator_output():
    data, result, _, _ = _context()
    assert conflict_count(result.conflicts) == len(result.conflicts) == 0


def test_total_maintenance_duration_only_counts_scheduled():
    data, result, _, _ = _context()
    scheduled = result.plan[result.plan.status == "Scheduled"]
    assert total_maintenance_duration_minutes(result.plan) == int(scheduled.duration_min.sum())


def test_train_impact_matches_weighted_disruption_metric():
    data, result, _, _ = _context()
    assert train_impact_minutes(result.plan) == result.metrics["weighted_disruption_minutes"]


def test_average_delay_impact_is_zero_with_no_scheduled_requests():
    empty_plan = pd.DataFrame(columns=["status", "disruption", "duration_min", "request_id", "asset_id"])
    assert average_delay_impact_minutes(empty_plan) == 0.0


def test_high_and_critical_risk_assets_addressed_are_grounded_in_the_risk_table():
    data, result, risk_table, _ = _context()
    high = high_risk_assets_addressed(result.plan, risk_table)
    critical = critical_risk_assets_addressed(result.plan, risk_table)
    assert critical <= high
    assert high <= scheduled_count(result.plan)


def test_estimated_possession_reduction_matches_coordination_engine():
    data, result, _, opportunities = _context()
    expected = sum(g["estimated_possession_reduction_minutes"] for g in opportunities)
    assert estimated_possession_reduction_minutes(opportunities) == expected


def test_schedule_utilization_is_a_percentage():
    data, result, _, _ = _context()
    value = schedule_utilization_pct(result.plan, data["windows"])
    assert 0 <= value <= 100
    assert value == result.metrics["block_utilization_pct"]


def test_risk_weighted_coverage_is_a_percentage_and_not_fabricated():
    data, result, risk_table, _ = _context()
    value = risk_weighted_maintenance_coverage_pct(data["requests"], result.plan, risk_table)
    assert 0 <= value <= 100


def test_risk_weighted_coverage_increases_when_more_high_risk_work_is_scheduled():
    data, result, risk_table, _ = _context()
    full_coverage_plan = result.plan.copy()
    full_coverage_plan["status"] = "Scheduled"
    baseline_value = risk_weighted_maintenance_coverage_pct(data["requests"], result.plan, risk_table)
    full_value = risk_weighted_maintenance_coverage_pct(data["requests"], full_coverage_plan, risk_table)
    assert full_value >= baseline_value


def test_compute_all_metrics_returns_all_twelve_and_matches_individual_functions():
    data, result, risk_table, opportunities = _context()
    metrics = compute_all_metrics(result.plan, result.conflicts, data["requests"], risk_table, data["windows"], opportunities)
    assert len(metrics) == 12
    assert metrics["scheduled_requests"] == scheduled_count(result.plan)
    assert metrics["conflicts"] == conflict_count(result.conflicts)


def test_compare_metrics_before_after_baseline_vs_optimized():
    data, result, risk_table, opportunities = _context()
    baseline = baseline_plan(data["requests"], data["trains"])
    baseline_metrics = compute_all_metrics(baseline.plan, baseline.conflicts, data["requests"], risk_table, data["windows"], opportunities)
    optimized_metrics = compute_all_metrics(result.plan, result.conflicts, data["requests"], risk_table, data["windows"], opportunities)
    comparison = compare_metrics(baseline_metrics, optimized_metrics)
    assert comparison["improvement"]["conflicts"] == optimized_metrics["conflicts"] - baseline_metrics["conflicts"]
    # the optimized plan must never have more conflicts than the naive baseline
    assert optimized_metrics["conflicts"] <= baseline_metrics["conflicts"]
