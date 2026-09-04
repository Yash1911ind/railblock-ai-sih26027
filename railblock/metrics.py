"""Centralized KPI/metrics calculations over real plan data.

Every function here is a pure calculation over a `PlanningResult.plan`,
`.conflicts`, and the already-computed risk/coordination tables — no
Streamlit imports, no calls to `optimize_blocks()`. UI code should call these
instead of computing metrics inline, so the same number is never computed
two different ways in two different tabs.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def scheduled_count(plan: pd.DataFrame) -> int:
    return int((plan.status == "Scheduled").sum()) if not plan.empty else 0


def deferred_count(plan: pd.DataFrame) -> int:
    return int((plan.status == "Deferred").sum()) if not plan.empty else 0


def conflict_count(conflicts: list[dict[str, Any]]) -> int:
    return len(conflicts)


def total_maintenance_duration_minutes(plan: pd.DataFrame) -> int:
    scheduled = plan[plan.status == "Scheduled"] if not plan.empty else plan
    return int(scheduled.duration_min.sum()) if not scheduled.empty else 0


def train_impact_minutes(plan: pd.DataFrame) -> int:
    scheduled = plan[plan.status == "Scheduled"] if not plan.empty else plan
    return int(scheduled.disruption.sum()) if not scheduled.empty else 0


def average_delay_impact_minutes(plan: pd.DataFrame) -> float:
    count = scheduled_count(plan)
    if count == 0:
        return 0.0
    return round(train_impact_minutes(plan) / count, 1)


def _scheduled_with_risk(plan: pd.DataFrame, risk_table: pd.DataFrame) -> pd.DataFrame:
    scheduled = plan[plan.status == "Scheduled"] if not plan.empty else plan
    if scheduled.empty or risk_table.empty:
        return scheduled.assign(risk_level=pd.Series(dtype="object"))
    return scheduled.merge(risk_table[["asset_id", "risk_level"]], on="asset_id", how="left")


def high_risk_assets_addressed(plan: pd.DataFrame, risk_table: pd.DataFrame) -> int:
    merged = _scheduled_with_risk(plan, risk_table)
    if merged.empty:
        return 0
    return int(merged.risk_level.isin(["HIGH", "CRITICAL"]).sum())


def critical_risk_assets_addressed(plan: pd.DataFrame, risk_table: pd.DataFrame) -> int:
    merged = _scheduled_with_risk(plan, risk_table)
    if merged.empty:
        return 0
    return int((merged.risk_level == "CRITICAL").sum())


def coordination_opportunity_count(opportunities: list[dict[str, Any]]) -> int:
    return len(opportunities)


def estimated_possession_reduction_minutes(opportunities: list[dict[str, Any]]) -> int:
    return sum(g["estimated_possession_reduction_minutes"] for g in opportunities)


def schedule_utilization_pct(plan: pd.DataFrame, windows_df: pd.DataFrame) -> float:
    scheduled = plan[plan.status == "Scheduled"] if not plan.empty else plan
    completed = int(scheduled.duration_min.sum()) if not scheduled.empty else 0
    total_window_minutes = max(1, int((windows_df.end_min - windows_df.start_min).sum())) if not windows_df.empty else 1
    return round(100 * completed / total_window_minutes, 1)


def risk_weighted_maintenance_coverage_pct(
    requests_df: pd.DataFrame, plan: pd.DataFrame, risk_table: pd.DataFrame
) -> float:
    """Share of risk-weighted maintenance need (duration x asset risk score)
    that is scheduled in the current plan, 0-100.

    This is a derived estimate, not a measured field outcome: it weights each
    request's requested duration by its asset's risk score and reports what
    fraction of that total weight the current plan schedules. Returns 0.0 if
    no request has a resolvable asset risk score.
    """
    if requests_df.empty or risk_table.empty:
        return 0.0
    merged = requests_df.merge(risk_table[["asset_id", "risk_score"]], on="asset_id", how="left")
    merged["risk_score"] = merged["risk_score"].fillna(0)
    total_weight = float((merged.duration_min * merged.risk_score).sum())
    if total_weight <= 0:
        return 0.0
    scheduled_ids = set(plan[plan.status == "Scheduled"].request_id) if not plan.empty else set()
    scheduled_rows = merged[merged.request_id.isin(scheduled_ids)]
    scheduled_weight = float((scheduled_rows.duration_min * scheduled_rows.risk_score).sum())
    return round(100 * scheduled_weight / total_weight, 1)


def compute_all_metrics(
    plan: pd.DataFrame,
    conflicts: list[dict[str, Any]],
    requests_df: pd.DataFrame,
    risk_table: pd.DataFrame,
    windows_df: pd.DataFrame,
    opportunities: list[dict[str, Any]],
) -> dict[str, Any]:
    """One dict with every metric above — the single source of truth reused
    across the Control Room, Analytics and Before/After panels.
    """
    return {
        "scheduled_requests": scheduled_count(plan),
        "deferred_requests": deferred_count(plan),
        "conflicts": conflict_count(conflicts),
        "total_maintenance_duration_minutes": total_maintenance_duration_minutes(plan),
        "train_impact_minutes": train_impact_minutes(plan),
        "average_delay_impact_minutes": average_delay_impact_minutes(plan),
        "high_risk_assets_addressed": high_risk_assets_addressed(plan, risk_table),
        "critical_risk_assets_addressed": critical_risk_assets_addressed(plan, risk_table),
        "coordination_opportunities": coordination_opportunity_count(opportunities),
        "estimated_possession_reduction_minutes": estimated_possession_reduction_minutes(opportunities),
        "schedule_utilization_pct": schedule_utilization_pct(plan, windows_df),
        "risk_weighted_maintenance_coverage_pct": risk_weighted_maintenance_coverage_pct(
            requests_df, plan, risk_table
        ),
    }


def compare_metrics(baseline_metrics: dict[str, Any], other_metrics: dict[str, Any]) -> dict[str, Any]:
    """Generic before/after diff over two `compute_all_metrics()` outputs."""
    numeric_keys = [key for key in baseline_metrics if isinstance(baseline_metrics[key], (int, float))]
    return {
        "before": baseline_metrics,
        "after": other_metrics,
        "improvement": {key: round(other_metrics[key] - baseline_metrics[key], 2) for key in numeric_keys},
    }
