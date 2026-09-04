"""What-if simulation: run hypothetical disruption scenarios without touching
the live schedule.

Original state -> temporary copy -> apply scenario -> optimize_blocks()
-> validate (built in) -> compare -> discard temporary state.

Every scenario funnels through `railblock.disruptions.replan_after_disruption`,
which itself reuses the existing CP-SAT `optimize_blocks()` solver — no
second optimizer is implemented here. `requests_df`/`trains_df`/`windows_df`
and any `current_result` passed in are read-only to this module; nothing is
written back to them or to session state by this module itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .disruptions import SUPPORTED_DISRUPTION_TYPES, replan_after_disruption
from .optimizer import PlanningResult

SUPPORTED_SCENARIO_TYPES = SUPPORTED_DISRUPTION_TYPES


@dataclass
class SimulationResult:
    scenarios: list[dict[str, Any]]
    current_result: PlanningResult
    simulated_result: PlanningResult
    comparison: dict[str, Any]
    simulated_requests: pd.DataFrame
    simulated_trains: pd.DataFrame
    simulated_windows: pd.DataFrame


def run_what_if_scenario(
    requests_df: pd.DataFrame,
    trains_df: pd.DataFrame,
    windows_df: pd.DataFrame,
    scenario: dict[str, Any] | list[dict[str, Any]],
    *,
    current_result: PlanningResult | None = None,
    time_limit: float = 5.0,
    cancelled_train_ids: set[str] | None = None,
) -> SimulationResult:
    """Simulate one or more disruptions (e.g. train delay, block unavailable,
    emergency maintenance, duration increase) against a temporary copy of the
    state. The caller's `requests_df`/`trains_df`/`windows_df` and
    `current_result` are left completely untouched — this is read-only, never
    a live schedule change.
    """
    scenarios = scenario if isinstance(scenario, list) else [scenario]
    invalid = [s.get("type") for s in scenarios if s.get("type") not in SUPPORTED_SCENARIO_TYPES]
    if invalid:
        raise ValueError(f"Unsupported scenario type(s): {invalid}. Supported: {SUPPORTED_SCENARIO_TYPES}")

    replan = replan_after_disruption(
        requests_df,
        trains_df,
        windows_df,
        scenarios,
        baseline_result=current_result,
        time_limit=time_limit,
        cancelled_train_ids=cancelled_train_ids,
    )

    return SimulationResult(
        scenarios=scenarios,
        current_result=replan.baseline_result,
        simulated_result=replan.result,
        comparison=replan.comparison,
        simulated_requests=replan.disrupted_requests,
        simulated_trains=replan.disrupted_trains,
        simulated_windows=replan.disrupted_windows,
    )
