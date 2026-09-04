"""RailBlock AI prototype package."""
from .approval import apply_approved_priorities, build_priority_review_table
from .audit import format_event, record_event
from .coordination import build_optimization_proposal, detect_coordination_opportunities, summarize_opportunities
from .demo import DemoScenarioResult, run_scenario
from .digital_twin import build_network_figure, build_section_states, get_section_detail
from .disruptions import ReplanResult, apply_disruption, apply_disruptions, replan_after_disruption
from .explain import explain_all, explain_recommendation
from .metrics import compare_metrics, compute_all_metrics
from .optimizer import PlanningResult, optimize_blocks
from .risk import assess_assets, calculate_asset_risk, get_risk_level, priority_number_for_level, suggest_priority
from .scenarios import SimulationResult, run_what_if_scenario
from .system_status import check_system_status

__all__ = [
    "PlanningResult",
    "optimize_blocks",
    "assess_assets",
    "calculate_asset_risk",
    "get_risk_level",
    "suggest_priority",
    "priority_number_for_level",
    "explain_all",
    "explain_recommendation",
    "detect_coordination_opportunities",
    "summarize_opportunities",
    "build_optimization_proposal",
    "apply_disruption",
    "apply_disruptions",
    "replan_after_disruption",
    "ReplanResult",
    "run_what_if_scenario",
    "SimulationResult",
    "build_section_states",
    "build_network_figure",
    "get_section_detail",
    "apply_approved_priorities",
    "build_priority_review_table",
    "compute_all_metrics",
    "compare_metrics",
    "run_scenario",
    "DemoScenarioResult",
    "record_event",
    "format_event",
    "check_system_status",
]
