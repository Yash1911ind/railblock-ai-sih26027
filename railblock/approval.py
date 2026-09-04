"""Controller approval workflow for AI-suggested priority.

The optimizer's manual `priority` column is never overwritten automatically.
`apply_approved_priorities()` is a pure data transformation that a caller
(the UI) invokes only after an explicit controller approval action — it is
never called from inside `optimize_blocks()` or any other automatic path.
"""
from __future__ import annotations

import pandas as pd

from .risk import priority_number_for_level


def build_priority_review_table(requests_df: pd.DataFrame, risk_table: pd.DataFrame) -> pd.DataFrame:
    """One row per request with its manual priority next to the AI-suggested
    priority/level and risk score — exactly what a controller needs to
    decide whether to approve.
    """
    merged = requests_df.merge(
        risk_table[["asset_id", "risk_score", "risk_level", "ai_suggested_priority"]],
        on="asset_id",
        how="left",
    )
    merged["ai_suggested_priority_number"] = merged["ai_suggested_priority"].map(priority_number_for_level)
    return merged


def apply_approved_priorities(requests_df: pd.DataFrame, approved_priorities: dict[str, int]) -> pd.DataFrame:
    """Return a NEW requests DataFrame with the manual priority overridden
    ONLY for request_ids present in `approved_priorities`. `requests_df` is
    never mutated, and nothing here calls `optimize_blocks()` — the caller
    decides when (and whether) to re-optimize with the result.
    """
    updated = requests_df.copy()
    for request_id, new_priority in approved_priorities.items():
        mask = updated.request_id == request_id
        if not mask.any():
            raise ValueError(f"Unknown request_id for approved priority: {request_id!r}")
        updated.loc[mask, "priority"] = int(new_priority)
    return updated
