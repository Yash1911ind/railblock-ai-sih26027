"""Transparent, rule-based asset maintenance risk engine.

This is a deterministic scoring formula over synthetic/demo asset attributes.
It is NOT a trained machine-learning model and makes no claim of predictive
accuracy against real railway failure data — it exists so a future ML model
could later be swapped in behind the same `calculate_asset_risk` contract.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

import pandas as pd

RISK_LEVEL_THRESHOLDS: list[tuple[str, int]] = [
    ("LOW", 24),
    ("MEDIUM", 49),
    ("HIGH", 74),
    ("CRITICAL", 100),
]

# weight given to each factor when it is available; renormalized over
# whichever factors are actually present for a given asset
FACTOR_WEIGHTS: dict[str, float] = {
    "condition": 0.4,
    "overdue": 0.3,
    "age": 0.1,
    "traffic": 0.1,
    "failures": 0.1,
}

# raw-value -> 0-100 sub-score scaling points, kept in one place so they are
# not scattered through the calculation
OVERDUE_SCALE_DAYS = 180
AGE_SCALE_YEARS = 30
TRAFFIC_SCALE_POINTS = 100
FAILURE_SCALE_COUNT = 5

NOTABLE_FACTOR_THRESHOLD = 40  # sub-score at/above this is surfaced as a reason

RECOMMENDED_ACTIONS: dict[str, str] = {
    "LOW": "Monitor during routine inspection; no schedule change needed.",
    "MEDIUM": "Schedule maintenance during an upcoming candidate window.",
    "HIGH": "Prioritize scheduling within the next available candidate window.",
    "CRITICAL": "Prioritize inspection/maintenance at the earliest feasible block.",
}

_FACTOR_LABELS: dict[str, tuple[str, str]] = {
    "condition": ("condition score", "condition_score"),
    "overdue": ("maintenance-overdue days", "last_maintenance_days"),
    "age": ("asset age", "asset_age_years"),
    "traffic": ("traffic/load exposure", "traffic_load_score"),
    "failures": ("historical failure count", "historical_failure_count"),
}

_FACTOR_DESCRIPTIONS = {
    "condition": lambda v: f"Condition score is poor ({v['condition_score']:.0f}/100).",
    "overdue": lambda v: f"Maintenance is overdue ({v['last_maintenance_days']:.0f} days since last service).",
    "age": lambda v: f"Asset age is high ({v['asset_age_years']:.0f} years).",
    "traffic": lambda v: f"Traffic/load exposure is high ({v['traffic_load_score']:.0f}/100).",
    "failures": lambda v: f"Historical failure count is high ({v['historical_failure_count']:.0f} recorded).",
}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _numeric(row: Mapping[str, Any], key: str) -> float | None:
    """Return a finite float for `key`, or None if missing/NaN/invalid."""
    if key not in row:
        return None
    value = row[key]
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(value):
        return None
    return value


def get_risk_level(score: float) -> str:
    """Map a 0-100 risk score to a discrete level using configurable bands."""
    score = _clamp(score)
    for level, upper_bound in RISK_LEVEL_THRESHOLDS:
        if score <= upper_bound:
            return level
    return RISK_LEVEL_THRESHOLDS[-1][0]


def suggest_priority(risk_score: float) -> str:
    """Advisory maintenance priority derived only from the risk score.

    This never reads or writes the manual `priority` column that the
    optimizer consumes.
    """
    return get_risk_level(risk_score)


# Maps an AI risk level onto the same 1-5 numeric scale the optimizer's
# manual `priority` column already uses. This mapping only has any effect on
# a plan once a controller has explicitly approved it — see railblock/approval.py.
PRIORITY_NUMBER_BY_LEVEL: dict[str, int] = {"LOW": 1, "MEDIUM": 2, "HIGH": 4, "CRITICAL": 5}


def priority_number_for_level(level: str) -> int:
    """Convert an AI risk level to a 1-5 optimizer-compatible priority number."""
    return PRIORITY_NUMBER_BY_LEVEL.get(level, 3)


def _to_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, "to_dict"):
        return dict(row.to_dict())
    return dict(row)


def _build_factors(sub_scores: dict[str, float], details: dict[str, float]) -> list[str]:
    factors = []
    for key, sub_score in sorted(sub_scores.items(), key=lambda item: item[1], reverse=True):
        if sub_score >= NOTABLE_FACTOR_THRESHOLD:
            factors.append(_FACTOR_DESCRIPTIONS[key](details))
    return factors


def calculate_asset_risk(asset_row: Any) -> dict[str, Any]:
    """Compute a transparent 0-100 risk score for one asset.

    `asset_row` may be a pandas Series (e.g. from `assets_df.iterrows()`) or a
    plain dict/mapping. Only columns that are actually present and numeric
    are used; missing or invalid optional columns are skipped rather than
    assumed, so old CSV files without extra columns keep working unchanged.
    """
    row = _to_dict(asset_row)
    asset_id = row.get("asset_id", "UNKNOWN")

    sub_scores: dict[str, float] = {}
    details: dict[str, float] = {}

    condition_score = _numeric(row, "condition_score")
    if condition_score is not None:
        condition_score = _clamp(condition_score)
        sub_scores["condition"] = _clamp(100 - condition_score)
        details["condition_score"] = condition_score

    last_maintenance_days = _numeric(row, "last_maintenance_days")
    if last_maintenance_days is not None and last_maintenance_days >= 0:
        sub_scores["overdue"] = _clamp(100 * last_maintenance_days / OVERDUE_SCALE_DAYS)
        details["last_maintenance_days"] = last_maintenance_days

    asset_age_years = _numeric(row, "asset_age_years")
    if asset_age_years is not None and asset_age_years >= 0:
        sub_scores["age"] = _clamp(100 * asset_age_years / AGE_SCALE_YEARS)
        details["asset_age_years"] = asset_age_years

    traffic_load_score = _numeric(row, "traffic_load_score")
    if traffic_load_score is not None and traffic_load_score >= 0:
        sub_scores["traffic"] = _clamp(100 * traffic_load_score / TRAFFIC_SCALE_POINTS)
        details["traffic_load_score"] = traffic_load_score

    historical_failure_count = _numeric(row, "historical_failure_count")
    if historical_failure_count is not None and historical_failure_count >= 0:
        sub_scores["failures"] = _clamp(100 * historical_failure_count / FAILURE_SCALE_COUNT)
        details["historical_failure_count"] = historical_failure_count

    if sub_scores:
        weight_total = sum(FACTOR_WEIGHTS[key] for key in sub_scores)
        risk_score = sum(sub_scores[key] * FACTOR_WEIGHTS[key] for key in sub_scores) / weight_total
    else:
        risk_score = 0.0
    risk_score = round(_clamp(risk_score), 1)
    risk_level = get_risk_level(risk_score)

    factors = _build_factors(sub_scores, details)
    if not factors:
        factors = ["No significant risk indicators found in the available asset data."]

    unavailable = [label for key, (label, _) in _FACTOR_LABELS.items() if key not in sub_scores]
    if unavailable:
        factors.append(
            "Factor(s) not scored — not present in this dataset: " + ", ".join(unavailable) + "."
        )

    return {
        "asset_id": asset_id,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "ai_suggested_priority": suggest_priority(risk_score),
        "factors": factors,
        "recommended_action": RECOMMENDED_ACTIONS[risk_level],
    }


def assess_assets(assets_df: pd.DataFrame) -> pd.DataFrame:
    """Return one risk-assessment row per asset without mutating `assets_df`."""
    records = [calculate_asset_risk(row) for _, row in assets_df.iterrows()]
    return pd.DataFrame.from_records(records)
