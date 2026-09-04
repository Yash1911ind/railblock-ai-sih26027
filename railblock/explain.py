"""Explain why the optimizer scheduled or deferred a maintenance request.

Reads only the already-computed `PlanningResult` (plan, validator conflicts,
and the candidate options the solver considered) plus the asset risk score.
It never re-runs or wraps the CP-SAT model.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

from .data import hhmm
from .risk import calculate_asset_risk

if TYPE_CHECKING:
    from .optimizer import PlanningResult


def explain_recommendation(
    request_id: str,
    result: "PlanningResult",
    assets_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Return a headline + grounded, dynamically generated reasons for one request."""
    matches = result.plan[result.plan.request_id == request_id]
    if matches.empty:
        raise ValueError(f"Unknown request_id: {request_id!r}")
    block = matches.iloc[0]
    scheduled = block.status == "Scheduled"
    options = (result.options_by_request or {}).get(request_id, [])
    reasons: list[str] = []

    if scheduled:
        reasons.append(
            f"Scheduled {hhmm(int(block.start_min))}–{hhmm(int(block.end_min))}, "
            f"inside the requested window {hhmm(int(block.earliest_start))}–{hhmm(int(block.latest_end))}."
        )
        request_conflicts = [c for c in result.conflicts if request_id in str(c.get("item", ""))]
        if request_conflicts:
            reasons.append(
                f"{len(request_conflicts)} conflict(s) were flagged by the independent validator for this request."
            )
        else:
            reasons.append("No protected-train or resource conflict was detected by the independent validator.")

        reasons.append(f"Weighted train disruption for the selected start is {int(block.disruption)} minute(s).")

        if len(options) > 1:
            lower_disruption_rejected = sum(1 for opt in options if opt["disruption"] < block.disruption)
            note = (
                f"; {lower_disruption_rejected} had lower disruption but were not chosen once priority and "
                "start-lateness trade-offs were weighed."
                if lower_disruption_rejected
                else "."
            )
            reasons.append(
                f"Chosen from {len(options)} feasible candidate start time(s) evaluated by the optimizer" + note
            )

        coordinated = result.plan[
            (result.plan.section_id == block.section_id)
            & (result.plan.window_id == block.window_id)
            & (result.plan.department != block.department)
            & (result.plan.status == "Scheduled")
            & (result.plan.request_id != request_id)
        ]
        if len(coordinated):
            departments = ", ".join(sorted(coordinated.department.unique()))
            reasons.append(
                f"{len(coordinated)} compatible task(s) from other department(s) ({departments}) share "
                f"section {block.section_id} in window {block.window_id} and could be coordinated."
            )
    else:
        if not options:
            reasons.append(
                "No candidate start time inside the requested window avoided a protected-train or "
                "resource conflict, so no feasible option existed for the optimizer to select."
            )
        else:
            reasons.append(
                f"{len(options)} candidate start time(s) were feasible, but none improved the constrained "
                "objective enough relative to competing requests sharing the same section, crew or window."
            )

    if assets_df is not None and "asset_id" in block.index:
        asset_matches = assets_df[assets_df.asset_id == block.asset_id]
        if not asset_matches.empty:
            risk = calculate_asset_risk(asset_matches.iloc[0])
            reasons.append(
                f"Asset {block.asset_id} risk score is {risk['risk_score']}/100 ({risk['risk_level']}); "
                f"AI-suggested priority is {risk['ai_suggested_priority']} versus manual priority {block.priority}."
            )

    headline = (
        f"Recommended: {block.request_id} scheduled in section {block.section_id}."
        if scheduled
        else f"Deferred: {block.request_id} could not be scheduled in this plan."
    )

    return {
        "request_id": request_id,
        "status": block.status,
        "headline": headline,
        "reasons": reasons,
    }


def explain_all(
    result: "PlanningResult",
    assets_df: pd.DataFrame | None = None,
) -> dict[str, dict[str, Any]]:
    """Explain every request in `result.plan`, keyed by request_id."""
    return {
        request_id: explain_recommendation(request_id, result, assets_df)
        for request_id in result.plan.request_id
    }
