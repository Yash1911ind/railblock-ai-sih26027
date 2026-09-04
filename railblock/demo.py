"""Deterministic demonstration scenarios over the existing synthetic dataset.

Every scenario is a thin orchestration over already-existing functions (the
risk engine, the coordination engine, `optimize_blocks()`, the disruption/
what-if engines, and the explainability engine) — nothing here computes a
result independently, and no outcome is hardcoded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from .coordination import detect_coordination_opportunities
from .disruptions import ReplanResult, replan_after_disruption
from .optimizer import PlanningResult, optimize_blocks
from .risk import assess_assets


@dataclass
class DemoScenarioResult:
    scenario_id: str
    title: str
    description: str
    result: PlanningResult
    extra: dict[str, Any] = field(default_factory=dict)


def _base_plan(data: dict[str, pd.DataFrame]) -> PlanningResult:
    return optimize_blocks(data["requests"], data["trains"], data["windows"])


def scenario_normal_planning(data: dict[str, pd.DataFrame]) -> DemoScenarioResult:
    result = _base_plan(data)
    return DemoScenarioResult(
        "normal_planning",
        "Normal Maintenance Planning",
        "Baseline CP-SAT optimization over the unmodified demo dataset.",
        result,
    )


def scenario_high_risk_asset(data: dict[str, pd.DataFrame]) -> DemoScenarioResult:
    risk_table = assess_assets(data["assets"])
    top_asset = risk_table.sort_values("risk_score", ascending=False).iloc[0]
    result = _base_plan(data)
    return DemoScenarioResult(
        "high_risk_asset",
        "High-Risk Asset",
        f"Highlights the highest-risk asset, {top_asset.asset_id}, via the existing risk engine.",
        result,
        extra={"top_asset": top_asset.to_dict()},
    )


def scenario_train_delay(
    data: dict[str, pd.DataFrame], train_id: str = "TR-101", delay_minutes: int = 20
) -> DemoScenarioResult:
    baseline = _base_plan(data)
    replan: ReplanResult = replan_after_disruption(
        data["requests"],
        data["trains"],
        data["windows"],
        {"type": "TRAIN_DELAY", "train_id": train_id, "delay_minutes": delay_minutes},
        baseline_result=baseline,
    )
    return DemoScenarioResult(
        "train_delay",
        f"Train {train_id} Delayed +{delay_minutes} Minutes",
        "Applies a train delay and re-plans using the same CP-SAT optimizer.",
        replan.result,
        extra={"baseline": baseline, "comparison": replan.comparison},
    )


def scenario_block_unavailable(data: dict[str, pd.DataFrame], window_id: str = "W-A1") -> DemoScenarioResult:
    baseline = _base_plan(data)
    replan: ReplanResult = replan_after_disruption(
        data["requests"],
        data["trains"],
        data["windows"],
        {"type": "BLOCK_UNAVAILABLE", "window_id": window_id},
        baseline_result=baseline,
    )
    return DemoScenarioResult(
        "block_unavailable",
        f"Candidate Window {window_id} Unavailable",
        "Removes a candidate window and re-plans using the same CP-SAT optimizer.",
        replan.result,
        extra={"baseline": baseline, "comparison": replan.comparison},
    )


def scenario_emergency_maintenance(
    data: dict[str, pd.DataFrame], section_id: str = "SEC-A", duration_min: int = 60
) -> DemoScenarioResult:
    baseline = _base_plan(data)
    asset_row = data["assets"][data["assets"].section_id == section_id].iloc[0]
    crew_row = data["resources"][data["resources"].department == "Engineering"].iloc[0]
    emergency_request = {
        "request_id": "MR-DEMO-EMERGENCY",
        "asset_id": asset_row.asset_id,
        "work_type": "Emergency inspection",
        "section_id": section_id,
        "department": "Engineering",
        "duration_min": duration_min,
        "priority": 5,
        "earliest_start": 0,
        "latest_end": 780,
        "crew_id": crew_row.crew_id,
    }
    replan: ReplanResult = replan_after_disruption(
        data["requests"],
        data["trains"],
        data["windows"],
        {"type": "EMERGENCY_MAINTENANCE", "request": emergency_request},
        baseline_result=baseline,
    )
    return DemoScenarioResult(
        "emergency_maintenance",
        "Emergency Maintenance",
        "Injects an emergency request and re-plans using the same CP-SAT optimizer.",
        replan.result,
        extra={"baseline": baseline, "comparison": replan.comparison},
    )


def scenario_multi_department_coordination(data: dict[str, pd.DataFrame]) -> DemoScenarioResult:
    result = _base_plan(data)
    opportunities = detect_coordination_opportunities(data["requests"], data["windows"])
    return DemoScenarioResult(
        "multi_department_coordination",
        "Multi-Department Coordination",
        "Runs the existing coordination engine over the demo dataset's requests.",
        result,
        extra={"opportunities": opportunities},
    )


SCENARIOS: dict[str, Callable[..., DemoScenarioResult]] = {
    "normal_planning": scenario_normal_planning,
    "high_risk_asset": scenario_high_risk_asset,
    "train_delay": scenario_train_delay,
    "block_unavailable": scenario_block_unavailable,
    "emergency_maintenance": scenario_emergency_maintenance,
    "multi_department_coordination": scenario_multi_department_coordination,
}


def run_scenario(scenario_id: str, data: dict[str, pd.DataFrame], **kwargs: Any) -> DemoScenarioResult:
    if scenario_id not in SCENARIOS:
        raise ValueError(f"Unknown demo scenario: {scenario_id!r}. Supported: {sorted(SCENARIOS)}")
    return SCENARIOS[scenario_id](data, **kwargs)
