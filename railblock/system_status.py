"""Runtime self-check for the System Status panel.

Each check confirms its engine's entry point is importable and minimally
callable. This never contacts any external system — none exists for this
prototype to connect to — it only verifies the modules already bundled in
this repository initialize correctly.
"""
from __future__ import annotations

from typing import Any


def _check_cp_sat() -> None:
    from ortools.sat.python import cp_model

    cp_model.CpModel()


def _check_validation() -> None:
    from .validation import validate_plan

    assert callable(validate_plan)


def _check_risk() -> None:
    from .risk import calculate_asset_risk

    assert callable(calculate_asset_risk)


def _check_coordination() -> None:
    from .coordination import detect_coordination_opportunities

    assert callable(detect_coordination_opportunities)


def _check_replanning() -> None:
    from .disruptions import replan_after_disruption

    assert callable(replan_after_disruption)


def _check_simulation() -> None:
    from .scenarios import run_what_if_scenario

    assert callable(run_what_if_scenario)


def _check_digital_twin() -> None:
    from .digital_twin import build_section_states

    assert callable(build_section_states)


_COMPONENT_CHECKS: tuple[tuple[str, Any], ...] = (
    ("CP-SAT Optimizer", _check_cp_sat),
    ("Validation Engine", _check_validation),
    ("Risk Engine", _check_risk),
    ("Coordination Engine", _check_coordination),
    ("Re-planning", _check_replanning),
    ("Simulation Engine", _check_simulation),
    ("Digital Twin", _check_digital_twin),
)


def check_system_status() -> list[dict[str, str]]:
    """Return one {component, status} record per engine, reflecting an
    actual runtime probe rather than a hardcoded "all green" list.
    """
    results: list[dict[str, str]] = []
    for name, probe in _COMPONENT_CHECKS:
        try:
            probe()
            results.append({"component": name, "status": "READY"})
        except Exception as exc:  # pragma: no cover - defensive, not expected in this repo
            results.append({"component": name, "status": f"ERROR: {exc}"})
    return results
