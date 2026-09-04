"""Digital Twin: a visualization/simulation layer over the existing plan.

This is NOT a live representation of railway infrastructure — there is no
real-time connectivity, sensors, or GPS anywhere in this module. It only
reshapes data already computed elsewhere (a `PlanningResult` from the
existing `optimize_blocks()`, plus the existing risk engine) for display.
It never calls `optimize_blocks()` itself and never invents a status,
position, or number that isn't derivable from the actual DataFrames passed
in — trains are shown at their scheduled/simulated time window, never a
live position.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .risk import RISK_LEVEL_THRESHOLDS, calculate_asset_risk

SECTION_STATUSES = ("AVAILABLE", "MAINTENANCE", "CONFLICT", "RESTRICTED")

_RISK_RANK = {level: index for index, (level, _) in enumerate(RISK_LEVEL_THRESHOLDS)}


def _conflict_touches_requests(conflict: dict[str, Any], request_ids: set[str]) -> bool:
    item = str(conflict.get("item", ""))
    return any(request_id in item for request_id in request_ids)


def section_status(
    section_id: str,
    plan_df: pd.DataFrame,
    conflicts: list[dict[str, Any]],
    trains_df: pd.DataFrame,
) -> str:
    """Derive one of SECTION_STATUSES from the actual plan/conflicts/trains.

    Precedence: a validator conflict outranks an ordinary maintenance block,
    which outranks a simulated temporary restriction, which outranks an
    otherwise-clear section. Nothing here is guessed.
    """
    section_plan = plan_df[plan_df.section_id == section_id] if not plan_df.empty else plan_df
    section_request_ids = set(section_plan.request_id) if not section_plan.empty else set()

    if any(_conflict_touches_requests(c, section_request_ids) for c in conflicts):
        return "CONFLICT"
    if not section_plan.empty and (section_plan.status == "Scheduled").any():
        return "MAINTENANCE"
    section_trains = trains_df[trains_df.section_id == section_id] if not trains_df.empty else trains_df
    if not section_trains.empty and section_trains.train_id.astype(str).str.startswith("RESTRICTION-").any():
        return "RESTRICTED"
    return "AVAILABLE"


def section_risk_level(section_id: str, assets_df: pd.DataFrame) -> str:
    """Highest risk level among this section's assets, via the existing risk
    engine (never recomputed differently). 'N/A' if the section has no assets.
    """
    section_assets = assets_df[assets_df.section_id == section_id]
    if section_assets.empty:
        return "N/A"
    levels = [calculate_asset_risk(row)["risk_level"] for _, row in section_assets.iterrows()]
    return max(levels, key=lambda level: _RISK_RANK.get(level, -1))


def build_section_states(
    result_plan: pd.DataFrame,
    conflicts: list[dict[str, Any]],
    assets_df: pd.DataFrame,
    trains_df: pd.DataFrame,
    windows_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    """One state record per known section, built only from actual data.

    Sections come from the union of assets/trains/windows section_id values
    — nothing is invented if a section happens to have no requests.
    """
    section_ids = sorted(
        set(assets_df.section_id) | set(trains_df.section_id) | set(windows_df.section_id)
    )
    states: list[dict[str, Any]] = []
    for section_id in section_ids:
        section_plan = result_plan[result_plan.section_id == section_id] if not result_plan.empty else result_plan
        scheduled = section_plan[section_plan.status == "Scheduled"] if not section_plan.empty else section_plan
        deferred = section_plan[section_plan.status == "Deferred"] if not section_plan.empty else section_plan
        section_trains = trains_df[trains_df.section_id == section_id]
        states.append(
            {
                "section_id": section_id,
                "status": section_status(section_id, result_plan, conflicts, trains_df),
                "risk_level": section_risk_level(section_id, assets_df),
                "scheduled_blocks": (
                    scheduled[["request_id", "department", "start_min", "end_min", "disruption"]].to_dict("records")
                    if not scheduled.empty
                    else []
                ),
                "deferred_requests": deferred["request_id"].tolist() if not deferred.empty else [],
                "trains": [
                    {
                        "train_id": row.train_id,
                        "train_name": row.train_name,
                        "start_min": int(row.start_min),
                        "end_min": int(row.end_min),
                        "importance": int(row.importance),
                        "can_delay": bool(row.can_delay),
                        "position_label": "Scheduled position (simulation)",
                    }
                    for _, row in section_trains.iterrows()
                ],
                "asset_count": int((assets_df.section_id == section_id).sum()),
            }
        )
    return states


def get_section_detail(section_states: list[dict[str, Any]], section_id: str) -> dict[str, Any] | None:
    return next((state for state in section_states if state["section_id"] == section_id), None)


def build_network_figure(section_states: list[dict[str, Any]]):
    """A simplified, schematic railway network view: SEC-A --- SEC-B --- SEC-C.

    Sections are placed evenly along one line in ID order — this is a
    schematic layout, not a geographic map, since no real-world position
    data exists in this dataset.
    """
    import plotly.graph_objects as go

    status_colors = {
        "AVAILABLE": "#2DD4A8",
        "MAINTENANCE": "#3B82F6",
        "CONFLICT": "#F97366",
        "RESTRICTED": "#F59E0B",
    }
    risk_symbols = {
        "LOW": "circle",
        "MEDIUM": "circle",
        "HIGH": "diamond",
        "CRITICAL": "diamond-wide",
        "N/A": "circle-open",
    }

    x_positions = list(range(len(section_states)))
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=x_positions,
            y=[0] * len(section_states),
            mode="lines",
            line=dict(color="rgba(151,170,190,0.4)", width=3),
            hoverinfo="skip",
            showlegend=False,
        )
    )
    for x, state in zip(x_positions, section_states):
        hover = (
            f"<b>{state['section_id']}</b><br>"
            f"Status: {state['status']}<br>"
            f"Risk: {state['risk_level']}<br>"
            f"Scheduled blocks: {len(state['scheduled_blocks'])}<br>"
            f"Deferred requests: {len(state['deferred_requests'])}<br>"
            f"Trains (scheduled position): {len(state['trains'])}"
        )
        figure.add_trace(
            go.Scatter(
                x=[x],
                y=[0],
                mode="markers+text",
                marker=dict(
                    size=36,
                    color=status_colors.get(state["status"], "#97AABE"),
                    symbol=risk_symbols.get(state["risk_level"], "circle"),
                    line=dict(color="rgba(255,255,255,0.55)", width=2),
                ),
                text=[f"{state['section_id']}<br>{state['status']}"],
                textposition="bottom center",
                textfont=dict(size=11, color="#DCE8F2"),
                hovertext=hover,
                hoverinfo="text",
                showlegend=False,
            )
        )
    figure.update_layout(
        height=230,
        margin=dict(l=30, r=30, t=20, b=55),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False, range=[-0.6, len(section_states) - 0.4]),
        yaxis=dict(visible=False, range=[-1, 1]),
    )
    return figure
