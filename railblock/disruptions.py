"""Represent operational disruptions and re-plan through the existing optimizer.

Every disruption is applied to fresh copies of `requests`/`trains`/`windows`
— the caller's original DataFrames are never mutated. Re-planning always
reuses the existing `optimize_blocks()` CP-SAT solver (which already runs the
independent validator internally); no second scheduler is implemented here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .coordination import detect_coordination_opportunities
from .optimizer import PlanningResult, optimize_blocks

SUPPORTED_DISRUPTION_TYPES = (
    "TRAIN_DELAY",
    "BLOCK_UNAVAILABLE",
    "EMERGENCY_MAINTENANCE",
    "DURATION_INCREASE",
    "TEMPORARY_RESTRICTION",
)

_REQUIRED_REQUEST_FIELDS = (
    "request_id",
    "asset_id",
    "work_type",
    "section_id",
    "department",
    "duration_min",
    "priority",
    "earliest_start",
    "latest_end",
    "crew_id",
)


def _apply_train_delay(requests_df, trains_df, windows_df, disruption):
    train_id = disruption.get("train_id")
    delay_minutes = disruption.get("delay_minutes")
    if train_id is None or delay_minutes is None:
        raise ValueError("TRAIN_DELAY requires 'train_id' and 'delay_minutes'.")
    if train_id not in set(trains_df.train_id):
        raise ValueError(f"Unknown train_id for TRAIN_DELAY: {train_id!r}")
    mask = trains_df.train_id == train_id
    trains_df.loc[mask, "start_min"] = trains_df.loc[mask, "start_min"] + int(delay_minutes)
    trains_df.loc[mask, "end_min"] = trains_df.loc[mask, "end_min"] + int(delay_minutes)
    return requests_df, trains_df, windows_df


def _apply_block_unavailable(requests_df, trains_df, windows_df, disruption):
    window_id = disruption.get("window_id")
    if window_id is None:
        raise ValueError("BLOCK_UNAVAILABLE requires 'window_id'.")
    if window_id not in set(windows_df.window_id):
        raise ValueError(f"Unknown window_id for BLOCK_UNAVAILABLE: {window_id!r}")
    windows_df = windows_df[windows_df.window_id != window_id].reset_index(drop=True)
    return requests_df, trains_df, windows_df


def _apply_emergency_maintenance(requests_df, trains_df, windows_df, disruption):
    request = disruption.get("request")
    if not isinstance(request, dict):
        raise ValueError("EMERGENCY_MAINTENANCE requires a 'request' dict.")
    missing = [field for field in _REQUIRED_REQUEST_FIELDS if field not in request]
    if missing:
        raise ValueError(f"EMERGENCY_MAINTENANCE request is missing field(s): {', '.join(missing)}")
    if request["request_id"] in set(requests_df.request_id):
        raise ValueError(f"request_id {request['request_id']!r} already exists.")
    new_row = {field: request[field] for field in _REQUIRED_REQUEST_FIELDS}
    requests_df = pd.concat([requests_df, pd.DataFrame([new_row])], ignore_index=True)
    return requests_df, trains_df, windows_df


def _apply_duration_increase(requests_df, trains_df, windows_df, disruption):
    request_id = disruption.get("request_id")
    additional_minutes = disruption.get("additional_minutes")
    if request_id is None or additional_minutes is None:
        raise ValueError("DURATION_INCREASE requires 'request_id' and 'additional_minutes'.")
    if request_id not in set(requests_df.request_id):
        raise ValueError(f"Unknown request_id for DURATION_INCREASE: {request_id!r}")
    mask = requests_df.request_id == request_id
    requests_df.loc[mask, "duration_min"] = requests_df.loc[mask, "duration_min"] + int(additional_minutes)
    return requests_df, trains_df, windows_df


def _apply_temporary_restriction(requests_df, trains_df, windows_df, disruption):
    section_id = disruption.get("section_id")
    start_min = disruption.get("start_min")
    end_min = disruption.get("end_min")
    if section_id is None or start_min is None or end_min is None:
        raise ValueError("TEMPORARY_RESTRICTION requires 'section_id', 'start_min' and 'end_min'.")
    if end_min <= start_min:
        raise ValueError("TEMPORARY_RESTRICTION 'end_min' must be after 'start_min'.")
    # Modeled as a synthetic non-delayable "train" occupying the section for
    # the restricted period: this reuses the optimizer's existing
    # protected-train exclusion logic in `_candidates()` exactly, with no
    # changes to optimizer.py.
    restriction_row = {
        "train_id": f"RESTRICTION-{len(trains_df) + 1}",
        "train_name": disruption.get("label", "Temporary infrastructure restriction"),
        "section_id": section_id,
        "start_min": int(start_min),
        "end_min": int(end_min),
        "importance": 5,
        "can_delay": False,
    }
    trains_df = pd.concat([trains_df, pd.DataFrame([restriction_row])], ignore_index=True)
    return requests_df, trains_df, windows_df


_HANDLERS = {
    "TRAIN_DELAY": _apply_train_delay,
    "BLOCK_UNAVAILABLE": _apply_block_unavailable,
    "EMERGENCY_MAINTENANCE": _apply_emergency_maintenance,
    "DURATION_INCREASE": _apply_duration_increase,
    "TEMPORARY_RESTRICTION": _apply_temporary_restriction,
}


def apply_disruption(
    requests_df: pd.DataFrame,
    trains_df: pd.DataFrame,
    windows_df: pd.DataFrame,
    disruption: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return new (requests, trains, windows) copies with `disruption` applied.

    The inputs are never mutated in place.
    """
    disruption_type = disruption.get("type")
    handler = _HANDLERS.get(disruption_type)
    if handler is None:
        raise ValueError(
            f"Unknown disruption type: {disruption_type!r}. Supported: {SUPPORTED_DISRUPTION_TYPES}"
        )
    return handler(requests_df.copy(), trains_df.copy(), windows_df.copy(), disruption)


def apply_disruptions(
    requests_df: pd.DataFrame,
    trains_df: pd.DataFrame,
    windows_df: pd.DataFrame,
    disruptions: list[dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Apply a sequence of disruptions, chaining each onto fresh copies."""
    for disruption in disruptions:
        requests_df, trains_df, windows_df = apply_disruption(
            requests_df, trains_df, windows_df, disruption
        )
    return requests_df, trains_df, windows_df


def compare_planning_metrics(
    before: PlanningResult,
    after: PlanningResult,
    *,
    before_windows: pd.DataFrame,
    after_windows: pd.DataFrame,
) -> dict[str, Any]:
    """Grounded before/after comparison built only from actual PlanningResult data."""

    def _snapshot(result: PlanningResult, windows: pd.DataFrame) -> dict[str, int]:
        scheduled = result.plan[result.plan.status == "Scheduled"]
        deferred = result.plan[result.plan.status == "Deferred"]
        opportunities = detect_coordination_opportunities(result.plan, windows)
        return {
            "scheduled_requests": len(scheduled),
            "deferred_requests": len(deferred),
            "conflicts": len(result.conflicts),
            "total_block_duration_minutes": int(scheduled.duration_min.sum()) if not scheduled.empty else 0,
            "train_impact_minutes": int(result.metrics.get("weighted_disruption_minutes", 0)),
            "coordination_opportunities": len(opportunities),
        }

    before_snapshot = _snapshot(before, before_windows)
    after_snapshot = _snapshot(after, after_windows)
    improvement = {key: after_snapshot[key] - before_snapshot[key] for key in before_snapshot}
    return {"before": before_snapshot, "after": after_snapshot, "improvement": improvement}


@dataclass
class ReplanResult:
    baseline_result: PlanningResult
    disrupted_requests: pd.DataFrame
    disrupted_trains: pd.DataFrame
    disrupted_windows: pd.DataFrame
    result: PlanningResult
    comparison: dict[str, Any]
    applied_disruptions: list[dict[str, Any]]


def replan_after_disruption(
    requests_df: pd.DataFrame,
    trains_df: pd.DataFrame,
    windows_df: pd.DataFrame,
    disruption: dict[str, Any] | list[dict[str, Any]],
    *,
    baseline_result: PlanningResult | None = None,
    time_limit: float = 5.0,
    cancelled_train_ids: set[str] | None = None,
) -> ReplanResult:
    """Apply one or more disruptions and re-plan using the existing CP-SAT optimizer.

    CURRENT PLAN -> DISRUPTION -> UPDATE STATE -> optimize_blocks() -> VALIDATION (built in)

    Pass an already-computed `baseline_result` (e.g. the plan already shown in
    the UI this rerun) to avoid solving twice. Neither `requests_df`,
    `trains_df` nor `windows_df` are mutated.
    """
    disruptions = disruption if isinstance(disruption, list) else [disruption]
    disrupted_requests, disrupted_trains, disrupted_windows = apply_disruptions(
        requests_df, trains_df, windows_df, disruptions
    )

    if baseline_result is None:
        baseline_result = optimize_blocks(
            requests_df,
            trains_df,
            windows_df,
            time_limit=time_limit,
            cancelled_train_ids=cancelled_train_ids,
        )

    new_result = optimize_blocks(
        disrupted_requests,
        disrupted_trains,
        disrupted_windows,
        time_limit=time_limit,
        cancelled_train_ids=cancelled_train_ids,
    )

    comparison = compare_planning_metrics(
        baseline_result, new_result, before_windows=windows_df, after_windows=disrupted_windows
    )

    return ReplanResult(
        baseline_result=baseline_result,
        disrupted_requests=disrupted_requests,
        disrupted_trains=disrupted_trains,
        disrupted_windows=disrupted_windows,
        result=new_result,
        comparison=comparison,
        applied_disruptions=disruptions,
    )
