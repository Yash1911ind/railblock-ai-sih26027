"""Multi-department coordination analysis (advisory layer).

Identifies maintenance requests in the same section whose *requested* time
windows could plausibly share a single common possession instead of running
as separate sequential blocks. This module never modifies the CP-SAT model in
`optimizer.py` — see docs/ALGORITHM.md ("Phase 2") for why true joint-block
scheduling stays advisory-only for now: it would require relaxing the
optimizer's same-section mutual-exclusion constraint and restructuring the
per-request reward/crew logic, which is a significant, higher-risk change.

Estimated savings here are a scheduling-time estimate only, not a measured
real-world railway operational saving.
"""
from __future__ import annotations

import itertools
from typing import Any

import pandas as pd

# This dataset's "Electrical" department covers OHE/traction work; labeled
# here for display purposes only. Grouping logic itself is department-agnostic
# and works with whatever values are actually present in the data.
DEPARTMENT_LABELS: dict[str, str] = {
    "Engineering": "Engineering",
    "S&T": "S&T",
    "Electrical": "Traction",
}


def department_label(raw_department: str) -> str:
    return DEPARTMENT_LABELS.get(raw_department, raw_department)


def _common_window(requests: list[pd.Series], duration: int) -> tuple[int, int] | None:
    lower = max(int(r.earliest_start) for r in requests)
    upper = min(int(r.latest_end) for r in requests) - duration
    if upper < lower:
        return None
    return lower, upper


def _containing_candidate_window(
    section_windows: pd.DataFrame, lower: int, upper: int, duration: int
) -> str | None:
    for _, window in section_windows.iterrows():
        if int(window.start_min) <= lower and upper + duration <= int(window.end_min):
            return window.window_id
    return None


def check_group_compatibility(
    requests: list[pd.Series], windows_df: pd.DataFrame
) -> dict[str, Any]:
    """Return whether `requests` could plausibly share one common possession.

    This is a scheduling-feasibility estimate over requested windows and
    candidate windows, not a railway safety certification. Coordination is
    only ever suggested, never assumed.
    """
    if len(requests) < 2:
        return {"compatible": False, "reason": "At least two requests are required to coordinate."}

    sections = {r.section_id for r in requests}
    if len(sections) != 1:
        return {"compatible": False, "reason": "Requests are not in the same section."}
    section_id = sections.pop()

    departments = {r.department for r in requests}
    if len(departments) < 2:
        return {
            "compatible": False,
            "reason": "All requests share the same department; nothing to coordinate.",
        }

    crews = [r.crew_id for r in requests]
    if len(set(crews)) != len(crews):
        return {
            "compatible": False,
            "reason": "Two or more requests share the same crew, which cannot perform simultaneous tasks.",
        }

    duration = max(int(r.duration_min) for r in requests)
    window = _common_window(requests, duration)
    if window is None:
        return {
            "compatible": False,
            "reason": "Requested windows do not overlap long enough to host the combined duration.",
        }
    lower, upper = window

    section_windows = windows_df[windows_df.section_id == section_id]
    hosting_window = _containing_candidate_window(section_windows, lower, upper, duration)
    if hosting_window is None:
        return {
            "compatible": False,
            "reason": "No single candidate window for this section can host the combined possession.",
        }

    individual_total = sum(int(r.duration_min) for r in requests)
    return {
        "compatible": True,
        "reason": f"Same section and overlapping requested windows fit inside candidate window {hosting_window}.",
        "section": section_id,
        "combined_duration_minutes": duration,
        "individual_duration_minutes": individual_total,
        "estimated_possession_reduction_minutes": individual_total - duration,
        "hosting_window_id": hosting_window,
        "shared_start_min": lower,
        "shared_end_min": lower + duration,
    }


def detect_coordination_opportunities(
    requests_df: pd.DataFrame, windows_df: pd.DataFrame
) -> list[dict[str, Any]]:
    """Return advisory coordination groups, largest-first, per section.

    Every request appears in at most one reported group. Requests that cannot
    be coordinated with anything are simply absent from the result — this
    function only reports opportunities; it never mutates or schedules
    anything, and `optimize_blocks()` is not called here.
    """
    groups: list[dict[str, Any]] = []
    group_counter = 0

    for section_id, section_requests in requests_df.groupby("section_id"):
        requests = [row for _, row in section_requests.iterrows()]
        used_ids: set[str] = set()
        for size in range(len(requests), 1, -1):
            for combo in itertools.combinations(requests, size):
                ids = {r.request_id for r in combo}
                if ids & used_ids:
                    continue
                outcome = check_group_compatibility(list(combo), windows_df)
                if outcome["compatible"]:
                    group_counter += 1
                    groups.append(
                        {
                            "group_id": f"CG-{group_counter:03d}",
                            "request_ids": sorted(ids),
                            "section": section_id,
                            "departments": sorted({r.department for r in combo}),
                            "department_labels": sorted({department_label(r.department) for r in combo}),
                            "compatible": True,
                            "reason": outcome["reason"],
                            "combined_duration_minutes": outcome["combined_duration_minutes"],
                            "individual_duration_minutes": outcome["individual_duration_minutes"],
                            "estimated_possession_reduction_minutes": outcome[
                                "estimated_possession_reduction_minutes"
                            ],
                            "shared_start_min": outcome["shared_start_min"],
                            "shared_end_min": outcome["shared_end_min"],
                        }
                    )
                    used_ids |= ids
    return groups


def summarize_opportunities(groups: list[dict[str, Any]]) -> dict[str, int]:
    """Total advisory savings across all detected groups, for a KPI summary."""
    return {
        "opportunity_count": len(groups),
        "total_estimated_reduction_minutes": sum(
            g["estimated_possession_reduction_minutes"] for g in groups
        ),
    }


def build_optimization_proposal(group: dict[str, Any], requests_df: pd.DataFrame) -> dict[str, Any]:
    """Preview of what a joint CP-SAT block would look like if a controller
    approves this coordination group — the "Optimization Proposal" step in
    Coordination Candidate -> Controller Approval -> Optimization Proposal.

    This is a data preview only. It does NOT call `optimize_blocks()` and it
    is NOT fed into the optimizer automatically. Phase 4 investigated wiring
    approved groups directly into the CP-SAT model (relaxing the same-section
    mutual-exclusion constraint for this group's requests) and found it would
    make the *independent* validator flag every coordinated block as a
    "Resource" conflict unless `validation.py` also became aware of approved
    coordination — which would compromise the validator's independence from
    the optimizer's own decisions. A safe alternative (merging the group into
    one multi-crew synthetic request) would require `crew_id` to become a set
    everywhere it's used in `optimizer.py` and `validation.py`, which is a
    genuine schema change, not a small additive one. Both paths were judged
    out of scope for a safe same-phase change — see docs/ALGORITHM.md
    ("Phase 4") for the full reasoning. This function exists so the proposal
    is concrete and inspectable today, while the CP-SAT wiring itself remains
    documented future work.
    """
    member_requests = requests_df[requests_df.request_id.isin(group["request_ids"])]
    return {
        "group_id": group["group_id"],
        "section": group["section"],
        "departments": group["departments"],
        "department_labels": group["department_labels"],
        "request_ids": group["request_ids"],
        "crews_involved": sorted(member_requests.crew_id.unique().tolist()),
        "shared_start_min": group["shared_start_min"],
        "shared_end_min": group["shared_end_min"],
        "combined_duration_minutes": group["combined_duration_minutes"],
        "individual_duration_minutes": group["individual_duration_minutes"],
        "estimated_possession_reduction_minutes": group["estimated_possession_reduction_minutes"],
        "status": "PROPOSAL ONLY — not yet applied to the CP-SAT optimizer (documented future enhancement)",
    }
