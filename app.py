"""RailBlock AI — SIH26027 demonstration dashboard."""

from html import escape
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from datetime import datetime

from railblock.approval import apply_approved_priorities, build_priority_review_table
from railblock.audit import format_event, record_event
from railblock.coordination import build_optimization_proposal, detect_coordination_opportunities, summarize_opportunities
from railblock.data import data_quality_report, hhmm, load_demo_data
from railblock.demo import run_scenario
from railblock.digital_twin import build_network_figure, build_section_states, get_section_detail
from railblock.disruptions import replan_after_disruption
from railblock.explain import explain_recommendation
from railblock.metrics import compare_metrics, compute_all_metrics
from railblock.optimizer import baseline_plan, optimize_blocks
from railblock.risk import assess_assets
from railblock.scenarios import run_what_if_scenario
from railblock.system_status import check_system_status


ROOT = Path(__file__).resolve().parent
DEMO_DATE = "2026-08-30"
DEPARTMENT_COLORS = {
    "Engineering": "#3B82F6",
    "S&T": "#A78BFA",
    "Electrical": "#F59E0B",
}
STATUS_BADGE_COLORS = {"AVAILABLE": "green", "MAINTENANCE": "blue", "CONFLICT": "red", "RESTRICTED": "orange"}
RISK_BADGE_COLORS = {"LOW": "green", "MEDIUM": "blue", "HIGH": "orange", "CRITICAL": "red", "N/A": "gray"}

st.set_page_config(
    page_title="RailBlock AI · SIH26027",
    page_icon=":material/train:",
    layout="wide",
    initial_sidebar_state="auto",
)
st.html(ROOT / "assets" / "railblock.css")


@st.cache_data
def demo_data() -> dict[str, pd.DataFrame]:
    """Load the deterministic demo inputs once per application process."""
    return load_demo_data()


def plan_snapshot(plan: pd.DataFrame) -> pd.DataFrame:
    """Return the UI fields needed for an honest previous/current comparison."""
    return plan[["request_id", "status", "start_min", "end_min"]].copy()


def compare_plans(previous: pd.DataFrame | None, current: pd.DataFrame) -> pd.DataFrame:
    """Describe schedule changes without altering the planning result."""
    if previous is None or previous.empty:
        return pd.DataFrame(columns=["Request", "Previous plan", "Updated plan", "Change"])

    def label(row: pd.Series) -> str:
        if row["status"] != "Scheduled" or pd.isna(row["start_min"]):
            return "Deferred"
        return f"{hhmm(row['start_min'])}–{hhmm(row['end_min'])}"

    previous_rows = previous.set_index("request_id")
    current_rows = current.set_index("request_id")
    changes: list[dict[str, str]] = []
    for request_id in current_rows.index:
        after = current_rows.loc[request_id]
        after_label = label(after)
        if request_id not in previous_rows.index:
            changes.append(
                {
                    "Request": request_id,
                    "Previous plan": "Did not exist",
                    "Updated plan": after_label,
                    "Change": "New request added",
                }
            )
            continue
        before = previous_rows.loc[request_id]
        before_label = label(before)
        if before_label == after_label:
            continue
        if before["status"] == "Scheduled" and after["status"] == "Scheduled":
            shift = int(after["start_min"] - before["start_min"])
            change = f"Shifted {shift:+d} min"
        elif after["status"] == "Scheduled":
            change = "Now scheduled"
        else:
            change = "Now deferred"
        changes.append(
            {
                "Request": request_id,
                "Previous plan": before_label,
                "Updated plan": after_label,
                "Change": change,
            }
        )
    return pd.DataFrame(changes)


def scenario_label(cancelled: set[str]) -> str:
    if not cancelled:
        return "Base simulated scenario"
    return f"Cancellation · {next(iter(cancelled))}"


def apply_replan() -> None:
    selected = st.session_state.cancelled_train_selection
    st.session_state.previous_plan_snapshot = st.session_state.get("active_plan_snapshot")
    st.session_state.previous_scenario_label = scenario_label(st.session_state.cancelled)
    st.session_state.cancelled = set() if selected == "None" else {selected}
    st.session_state.replan_pending = True
    st.session_state.reset_notice = False


def reset_scenario() -> None:
    st.session_state.cancelled = set()
    st.session_state.cancelled_train_selection = "None"
    st.session_state.replan_pending = False
    st.session_state.replan_summary = None
    st.session_state.reset_notice = True


def reset_demo_state() -> None:
    """Restore session state to the base scenario. Never touches source CSVs
    or `st.cache_data` — `demo_data()` always re-reads the same files, so the
    original DataFrames are unaffected by anything that happens in a session.
    """
    reset_scenario()
    st.session_state.controller_decisions = {}
    st.session_state.audit_log = []
    st.session_state.approved_priorities = {}
    st.session_state.priority_replan_result = None
    st.session_state.coordination_proposals = {}
    st.session_state.replan_disruption_result = None
    st.session_state.whatif_simulation_result = None
    st.session_state.demo_reset_notice = True


def render_header() -> None:
    st.html(
        """
        <header class="rb-hero">
          <div class="rb-brand-lockup">
            <div class="rb-mark" aria-hidden="true">
              <span class="material-symbols-rounded">train</span>
            </div>
            <div>
              <div class="rb-eyebrow">AI-powered maintenance block planning</div>
              <h1>RailBlock <span>AI</span></h1>
              <p>Constraint-aware possession planning for safer, more available railway assets.</p>
            </div>
          </div>
          <div class="rb-hero-meta">
            <span class="rb-demo-dot"><i></i> Simulation / demo</span>
            <strong>SIH26027</strong>
            <span>Crafters· Chandighar University</span>
          </div>
        </header>
        """
    )


def render_data_notice() -> None:
    st.html(
        """
        <div class="rb-data-notice" role="status">
          <span class="material-symbols-rounded" aria-hidden="true">verified_user</span>
          <div><strong>Deterministic simulation</strong><br>
          Every asset, train, time window and KPI is simulated/demo data—not official Indian Railways operational data.</div>
        </div>
        """
    )


def render_section_heading(eyebrow: str, title: str, description: str) -> None:
    st.html(
        f"""
        <div class="rb-section-heading">
          <span>{escape(eyebrow)}</span>
          <h2>{escape(title)}</h2>
          <p>{escape(description)}</p>
        </div>
        """
    )


def render_kpis(result, baseline) -> None:
    kpis = [
        ("event_available", "Requests planned", f"{result.metrics['scheduled_requests']}/{result.metrics['total_requests']}", "Priority-aware schedule", "success"),
        ("shield", "Protected conflicts", str(result.metrics["protected_train_conflicts"]), f"From {len(baseline.conflicts)} baseline issues", "success"),
        ("construction", "Maintenance coverage", f"{result.metrics['maintenance_completion_pct']}%", "Requested minutes · simulated", "success"),
        ("swap_horiz", "Operational interaction", str(result.metrics["weighted_disruption_minutes"]), "Weighted minutes · simulated", "neutral"),
        ("timer", "Solver time", f"{result.solve_seconds:.3f}s", "Current demo run", "neutral"),
    ]
    cards = "".join(
        f"""
        <article class="rb-kpi-card rb-kpi-{tone}">
          <div class="rb-kpi-top"><span class="material-symbols-rounded">{icon}</span><i></i></div>
          <div class="rb-kpi-label">{escape(label)}</div>
          <div class="rb-kpi-value">{escape(value)}</div>
          <div class="rb-kpi-note">{escape(note)}</div>
        </article>
        """
        for icon, label, value, note, tone in kpis
    )
    st.html(f'<div class="rb-kpi-grid">{cards}</div>')


def render_before_after(result, baseline) -> None:
    st.html(
        f"""
        <section class="rb-comparison" aria-label="Simulated before and after comparison">
          <div class="rb-comparison-head">
            <div><span>Decision impact</span><h2>Before vs after</h2></div>
            <span class="rb-sim-chip">Simulated demo result</span>
          </div>
          <div class="rb-comparison-grid">
            <article class="rb-before-card">
              <div class="rb-result-label"><span class="material-symbols-rounded">warning</span> Before</div>
              <div class="rb-result-value">{len(baseline.conflicts)}</div>
              <div class="rb-result-unit">conflicts</div>
              <p>Naive earliest-start baseline schedules first and detects conflicts afterward.</p>
            </article>
            <div class="rb-optimize-bridge">
              <span class="material-symbols-rounded">arrow_forward</span>
              <strong>Optimize</strong>
              <small>CP-SAT + rules</small>
            </div>
            <article class="rb-after-card">
              <div class="rb-result-label"><span class="material-symbols-rounded">verified</span> After</div>
              <div class="rb-result-value">{len(result.conflicts)}</div>
              <div class="rb-result-unit">validator conflicts</div>
              <p>Recommended plan is checked independently after optimization.</p>
            </article>
          </div>
          <div class="rb-result-strip">
            <div><strong>{result.metrics['scheduled_requests']}/{result.metrics['total_requests']}</strong><span>requests scheduled</span></div>
            <div><strong>{result.metrics['maintenance_completion_pct']}%</strong><span>simulated maintenance coverage</span></div>
            <div><strong>{escape(result.status)}</strong><span>solver status</span></div>
          </div>
        </section>
        """
    )


def render_replan_summary(summary: dict | None) -> None:
    if not summary:
        return
    changes = summary["changes"]
    change_count = len(changes)
    st.html(
        f"""
        <section class="rb-scenario-result">
          <div class="rb-scenario-icon"><span class="material-symbols-rounded">published_with_changes</span></div>
          <div class="rb-scenario-copy">
            <span>Scenario updated</span>
            <h3>Plan re-optimized successfully</h3>
            <p>{escape(summary['previous_scenario'])} → {escape(summary['current_scenario'])}</p>
          </div>
          <div class="rb-scenario-stats">
            <div><strong>{escape(summary['status'])}</strong><span>solver</span></div>
            <div><strong>{summary['conflicts']}</strong><span>conflicts</span></div>
            <div><strong>{summary['planned']}</strong><span>planned</span></div>
            <div><strong>{change_count}</strong><span>changed</span></div>
          </div>
        </section>
        """
    )
    if change_count:
        with st.expander(
            f"Inspect {change_count} changed request{'s' if change_count != 1 else ''}",
            icon=":material/compare_arrows:",
        ):
            st.dataframe(
                changes,
                hide_index=True,
                width="stretch",
                column_config={
                    "Request": st.column_config.TextColumn(width="small", pinned=True),
                    "Previous plan": st.column_config.TextColumn(width="medium"),
                    "Updated plan": st.column_config.TextColumn(width="medium"),
                    "Change": st.column_config.TextColumn(width="medium"),
                },
            )
    else:
        st.info(
            "The selected cancellation was not a binding constraint for the recommended schedule, so request timings did not change.",
            icon=":material/info:",
        )


def render_system_status_strip(result, demo_mode: bool) -> None:
    status_ok = result.status in {"OPTIMAL", "FEASIBLE"}
    mode_label = "DEMO / SIMULATION MODE" + (" · Demo walkthrough ON" if demo_mode else "")
    st.html(
        f"""
        <div class="rb-status-strip">
          <span class="rb-status-live"><i></i> {"SYSTEM OPERATIONAL" if status_ok else "SYSTEM ATTENTION"}</span>
          <span>Simulation date: <strong>{escape(DEMO_DATE)}</strong></span>
          <span>Rendered: <strong>{escape(datetime.now().strftime('%H:%M:%S'))}</strong></span>
          <span>CP-SAT status: <strong>{escape(result.status)}</strong></span>
          <span>{escape(mode_label)}</span>
        </div>
        """
    )


def render_control_room_kpis(result, risk_table: pd.DataFrame) -> None:
    deferred_count = result.metrics["total_requests"] - result.metrics["scheduled_requests"]
    critical_assets = int((risk_table["risk_level"] == "CRITICAL").sum())
    kpis = [
        ("route", "Active blocks", str(result.metrics["scheduled_requests"]), "Scheduled in current CP-SAT plan", "success"),
        ("priority_high", "Critical assets", str(critical_assets), "AI risk level CRITICAL", "success" if critical_assets == 0 else "neutral"),
        ("pending_actions", "Pending maintenance", str(deferred_count), "Requests awaiting a feasible block", "neutral"),
        ("error", "Conflicts", str(len(result.conflicts)), "Independent validator", "success" if not result.conflicts else "neutral"),
        ("schedule", "Deferred requests", str(deferred_count), "Not selected in this CP-SAT run", "neutral"),
        ("swap_horiz", "Estimated delay impact", f"{result.metrics['weighted_disruption_minutes']} min", "Weighted minutes · simulated", "neutral"),
    ]
    cards = "".join(
        f"""
        <article class="rb-kpi-card rb-kpi-{tone}">
          <div class="rb-kpi-top"><span class="material-symbols-rounded">{icon}</span><i></i></div>
          <div class="rb-kpi-label">{escape(label)}</div>
          <div class="rb-kpi-value">{escape(value)}</div>
          <div class="rb-kpi-note">{escape(note)}</div>
        </article>
        """
        for icon, label, value, note, tone in kpis
    )
    st.html(f'<div class="rb-kpi-grid rb-kpi-grid-6">{cards}</div>')


def build_operational_alerts(result, risk_table: pd.DataFrame, opportunities: list[dict]) -> list[dict]:
    """Data-driven alerts only — every entry traces to a real value already computed above."""
    alerts: list[dict] = []
    for _, row in risk_table[risk_table["risk_level"] == "CRITICAL"].iterrows():
        alerts.append(
            {
                "severity": "CRITICAL",
                "message": f"Asset {row.asset_name} ({row.asset_id}) has AI risk score {row.risk_score}/100.",
                "source": "AI Asset Health",
                "action": row.recommended_action,
            }
        )
    for conflict in result.conflicts:
        alerts.append(
            {
                "severity": "HIGH",
                "message": f"{conflict['type']} conflict on {conflict['item']}: {conflict['detail']}",
                "source": "Independent validator",
                "action": "Review the recommended plan before controller approval.",
            }
        )
    deferred = result.plan[result.plan.status == "Deferred"]
    if not deferred.empty:
        alerts.append(
            {
                "severity": "MEDIUM",
                "message": f"{len(deferred)} maintenance request(s) deferred: {', '.join(deferred.request_id)}.",
                "source": "CP-SAT optimizer",
                "action": "Review in Block Optimizer; consider a coordination opportunity or a future window.",
            }
        )
    if opportunities:
        total_saving = sum(g["estimated_possession_reduction_minutes"] for g in opportunities)
        alerts.append(
            {
                "severity": "LOW",
                "message": f"{len(opportunities)} multi-department coordination opportunity(ies) available (≈{total_saving} min estimated reduction).",
                "source": "Coordination engine",
                "action": "Review in the Coordination tab and approve if appropriate.",
            }
        )
    replan_state = st.session_state.get("replan_disruption_result")
    if replan_state and replan_state.result.conflicts:
        alerts.append(
            {
                "severity": "HIGH",
                "message": f"Simulated disruption re-plan still has {len(replan_state.result.conflicts)} conflict(s).",
                "source": "Dynamic Re-planning",
                "action": "Open the Re-planning tab to review before approval.",
            }
        )
    severity_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    alerts.sort(key=lambda a: severity_rank.get(a["severity"], 9))
    return alerts


def render_alert_center(alerts: list[dict]) -> None:
    if not alerts:
        st.success("✓ No critical operational alerts", icon=":material/verified:")
        return
    severity_style = {
        "CRITICAL": (st.error, ":material/emergency_home:"),
        "HIGH": (st.error, ":material/error:"),
        "MEDIUM": (st.warning, ":material/warning:"),
        "LOW": (st.info, ":material/info:"),
    }
    for alert in alerts:
        renderer, icon = severity_style.get(alert["severity"], (st.info, ":material/info:"))
        renderer(
            f"**[{alert['severity']}]** {alert['message']}  \n"
            f"Source: {alert['source']} · Recommended: {alert['action']}",
            icon=icon,
        )


def render_controller_actions(item_key: str) -> None:
    """Session-state-only controller review action. Never contacts any external system."""
    decision = st.session_state.controller_decisions.get(item_key)
    action_cols = st.columns([1, 1, 1, 2])
    if action_cols[0].button("Approve", key=f"approve_{item_key}", icon=":material/check_circle:"):
        st.session_state.controller_decisions[item_key] = "APPROVED"
    if action_cols[1].button("Modify", key=f"modify_{item_key}", icon=":material/edit:"):
        st.session_state.controller_decisions[item_key] = "MODIFY REQUESTED"
    if action_cols[2].button("Reject", key=f"reject_{item_key}", icon=":material/cancel:"):
        st.session_state.controller_decisions[item_key] = "REJECTED"
    with action_cols[3]:
        if decision:
            st.badge(
                decision,
                color={"APPROVED": "green", "REJECTED": "red", "MODIFY REQUESTED": "orange"}.get(decision, "gray"),
            )
    st.html('<div class="rb-controller-note">Prototype action — no external railway system is controlled.</div>')


def render_active_blocks_panel(result, risk_table: pd.DataFrame) -> None:
    scheduled = result.plan[result.plan.status == "Scheduled"].copy()
    if scheduled.empty:
        st.info("No active blocks in the current recommended plan.", icon=":material/info:")
        return
    risk_by_asset = risk_table.set_index("asset_id")["risk_level"].to_dict()
    for _, block in scheduled.sort_values(["section_id", "start_min"]).iterrows():
        with st.container(border=True):
            head_col, status_col = st.columns([3, 1])
            with head_col:
                st.markdown(
                    f"**{block.request_id}** · Section {block.section_id} · "
                    f"{hhmm(block.start_min)}–{hhmm(block.end_min)} · {block.department}"
                )
            with status_col:
                st.badge("MAINTENANCE", color=STATUS_BADGE_COLORS["MAINTENANCE"])
            info_cols = st.columns(4)
            info_cols[0].caption(f"Department: {block.department}")
            info_cols[1].caption(f"Risk: {risk_by_asset.get(block.asset_id, 'N/A')}")
            info_cols[2].caption(f"Train impact: {int(block.disruption)} min")
            info_cols[3].caption(f"Crew: {block.crew_id}")
            render_controller_actions(f"block:{block.request_id}")


def render_ai_command_center(risk_table: pd.DataFrame, result, data: dict) -> None:
    if risk_table.empty:
        st.info("No asset risk data available.", icon=":material/info:")
        return
    top_asset = risk_table.sort_values("risk_score", ascending=False).iloc[0]
    with st.container(border=True):
        st.markdown("#### :material/emergency_home: Critical Asset")
        badge_col, meta_col = st.columns([1, 3])
        with badge_col:
            st.badge(top_asset.risk_level, color=RISK_BADGE_COLORS.get(top_asset.risk_level, "gray"))
        with meta_col:
            st.markdown(f"**{top_asset.asset_name}** ({top_asset.asset_id}) · Section {top_asset.section_id}")
        st.progress(int(top_asset.risk_score) / 100, text=f"Risk score: {top_asset.risk_score}/100")
        st.markdown("**Reasons:**")
        for factor in top_asset.factors:
            st.markdown(f"- {factor}")
        st.markdown(f"**Recommended action:** {top_asset.recommended_action}")

    candidate_requests = data["requests"][data["requests"].asset_id == top_asset.asset_id]
    scheduled_ids = set(result.plan[result.plan.status == "Scheduled"].request_id)
    candidate_request_id = next((rid for rid in candidate_requests.request_id if rid in scheduled_ids), None)
    if candidate_request_id is None:
        scheduled_plan = result.plan[result.plan.status == "Scheduled"]
        if not scheduled_plan.empty:
            candidate_request_id = scheduled_plan.sort_values("priority", ascending=False).iloc[0].request_id

    if candidate_request_id is not None:
        block = result.plan[result.plan.request_id == candidate_request_id].iloc[0]
        with st.container(border=True):
            st.markdown("#### :material/route: Recommended Maintenance Block")
            st.markdown(f"**{block.request_id}** · {hhmm(block.start_min)} — {hhmm(block.end_min)}")
            explanation = explain_recommendation(candidate_request_id, result, data["assets"])
            for reason in explanation["reasons"]:
                st.markdown(f"✓ {reason}")
            render_controller_actions(f"recommendation:{candidate_request_id}")


def render_coordination_widget(opportunities: list[dict]) -> None:
    if not opportunities:
        st.info("No coordination opportunities in the current demo dataset.", icon=":material/info:")
        return
    for group in opportunities:
        with st.container(border=True):
            st.markdown(f"**Section {group['section']}** · {', '.join(group['department_labels'])}")
            st.caption(f"Requests: {', '.join(group['request_ids'])}")
            st.markdown(f"Estimated reduction: **{group['estimated_possession_reduction_minutes']} min**")
            decision = st.session_state.controller_decisions.get(f"coordination:{group['group_id']}")
            if decision:
                st.badge(decision, color={"APPROVED": "green", "REJECTED": "red"}.get(decision, "gray"))
            else:
                st.caption("AI-suggested coordination · Controller approval required.")
            st.caption("Approve or reject in the 🔗 Coordination tab.")


def render_disruption_widget() -> None:
    replan_state = st.session_state.get("replan_disruption_result")
    if not replan_state:
        st.success("✓ No active disruptions", icon=":material/verified:")
        return
    disruption = replan_state.applied_disruptions[0]
    st.markdown(f"**{disruption.get('type', 'DISRUPTION')}**")
    st.caption(str({k: v for k, v in disruption.items() if k != "request"}))
    comparison = replan_state.comparison
    metric_cols = st.columns(3)
    metric_cols[0].metric(
        "Conflicts", comparison["after"]["conflicts"],
        delta=comparison["improvement"]["conflicts"], delta_color="inverse",
    )
    metric_cols[1].metric(
        "Deferred", comparison["after"]["deferred_requests"],
        delta=comparison["improvement"]["deferred_requests"], delta_color="inverse",
    )
    metric_cols[2].metric(
        "Train impact (min)", comparison["after"]["train_impact_minutes"],
        delta=comparison["improvement"]["train_impact_minutes"], delta_color="inverse",
    )
    st.caption("Full detail available in the 🚨 Re-planning tab.")


METRIC_LABELS: dict[str, str] = {
    "scheduled_requests": "Scheduled requests",
    "deferred_requests": "Deferred requests",
    "conflicts": "Conflicts",
    "total_maintenance_duration_minutes": "Maintenance duration (min)",
    "train_impact_minutes": "Train impact (min)",
    "average_delay_impact_minutes": "Average delay impact (min)",
    "high_risk_assets_addressed": "High-risk assets addressed",
    "critical_risk_assets_addressed": "Critical-risk assets addressed",
    "coordination_opportunities": "Coordination opportunities",
    "estimated_possession_reduction_minutes": "Estimated possession reduction (min)",
    "schedule_utilization_pct": "Schedule utilization (%)",
    "risk_weighted_maintenance_coverage_pct": "Risk-weighted maintenance coverage (%, estimated)",
}


def render_metrics_comparison_table(comparison: dict, before_label: str, after_label: str) -> None:
    rows = [
        {
            "Metric": label,
            before_label: comparison["before"][key],
            after_label: comparison["after"][key],
            "Change": comparison["improvement"][key],
        }
        for key, label in METRIC_LABELS.items()
    ]
    table = pd.DataFrame(rows).set_index("Metric")
    st.dataframe(table, width="stretch")


def render_network_view(section_states: list[dict], key_prefix: str, *, interactive: bool) -> None:
    st.html(
        """
        <div class="rb-twin-legend">
          <span><i style="background:#2DD4A8"></i> AVAILABLE</span>
          <span><i style="background:#3B82F6"></i> MAINTENANCE</span>
          <span><i style="background:#F97366"></i> CONFLICT</span>
          <span><i style="background:#F59E0B"></i> RESTRICTED</span>
          <span>Marker shape: risk level (circle=LOW/MEDIUM, diamond=HIGH/CRITICAL)</span>
        </div>
        """
    )
    figure = build_network_figure(section_states)
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False}, key=f"{key_prefix}_network_figure")

    if not interactive:
        return None

    selected_section = st.selectbox(
        "Select section",
        [state["section_id"] for state in section_states],
        key=f"{key_prefix}_section_selector",
    )
    detail = get_section_detail(section_states, selected_section)
    if not detail:
        return None
    with st.container(border=True):
        head_col, status_col, risk_col = st.columns([2, 1, 1])
        with head_col:
            st.markdown(f"**Section {detail['section_id']}**")
        with status_col:
            st.badge(detail["status"], color=STATUS_BADGE_COLORS.get(detail["status"], "gray"))
        with risk_col:
            st.badge(f"Risk: {detail['risk_level']}", color=RISK_BADGE_COLORS.get(detail["risk_level"], "gray"))

        st.markdown(f"**Active block(s):** {len(detail['scheduled_blocks'])}")
        for block in detail["scheduled_blocks"]:
            st.caption(
                f"{block['request_id']} · {block['department']} · "
                f"{hhmm(block['start_min'])}–{hhmm(block['end_min'])} · "
                f"train impact {int(block['disruption'])} min"
            )
        if detail["deferred_requests"]:
            st.markdown(f"**Deferred maintenance requests:** {', '.join(detail['deferred_requests'])}")

        st.markdown(f"**Trains (scheduled/simulation position):** {len(detail['trains'])}")
        for train in detail["trains"]:
            protection = "protected" if not train["can_delay"] else "delay-tolerant"
            st.caption(
                f"{train['train_id']} · {train['train_name']} · "
                f"{hhmm(train['start_min'])}–{hhmm(train['end_min'])} · {protection} · {train['position_label']}"
            )
    return None


data = demo_data()
st.session_state.setdefault("cancelled", set())
st.session_state.setdefault("cancelled_train_selection", "None")
st.session_state.setdefault("active_plan_snapshot", None)
st.session_state.setdefault("previous_plan_snapshot", None)
st.session_state.setdefault("previous_scenario_label", "Base simulated scenario")
st.session_state.setdefault("replan_pending", False)
st.session_state.setdefault("replan_summary", None)
st.session_state.setdefault("reset_notice", False)
st.session_state.setdefault("controller_decisions", {})
st.session_state.setdefault("demo_mode", False)
st.session_state.setdefault("audit_log", [])
st.session_state.setdefault("approved_priorities", {})
st.session_state.setdefault("priority_replan_result", None)
st.session_state.setdefault("coordination_proposals", {})
st.session_state.setdefault("demo_reset_notice", False)

result = optimize_blocks(
    data["requests"],
    data["trains"],
    data["windows"],
    cancelled_train_ids=st.session_state.cancelled,
)
baseline = baseline_plan(data["requests"], data["trains"])

# Computed once per rerun and reused across the Control Room, Digital Twin,
# Coordination and Analytics tabs — never recomputed with a second CP-SAT
# solve just to render a dashboard card.
risk_table = assess_assets(data["assets"]).merge(
    data["assets"][["asset_id", "asset_name", "section_id"]], on="asset_id", how="left"
)
opportunities = detect_coordination_opportunities(data["requests"], data["windows"])
opportunity_summary = summarize_opportunities(opportunities)
section_states = build_section_states(result.plan, result.conflicts, data["assets"], data["trains"], data["windows"])
priority_review_table = build_priority_review_table(data["requests"], risk_table)
current_metrics = compute_all_metrics(result.plan, result.conflicts, data["requests"], risk_table, data["windows"], opportunities)
baseline_metrics = compute_all_metrics(baseline.plan, baseline.conflicts, data["requests"], risk_table, data["windows"], opportunities)
system_status_checks = check_system_status()
quality_report = data_quality_report(data)

if st.session_state.replan_pending:
    changes = compare_plans(st.session_state.previous_plan_snapshot, result.plan)
    st.session_state.replan_summary = {
        "previous_scenario": st.session_state.previous_scenario_label,
        "current_scenario": scenario_label(st.session_state.cancelled),
        "status": result.status,
        "conflicts": len(result.conflicts),
        "planned": f"{result.metrics['scheduled_requests']}/{result.metrics['total_requests']}",
        "changes": changes,
    }
    st.session_state.replan_pending = False

st.session_state.active_plan_snapshot = plan_snapshot(result.plan)


with st.sidebar:
    st.html(
        """
        <div class="rb-control-title">
          <span class="material-symbols-rounded">tune</span>
          <div><span>Operations console</span><strong>Control panel</strong></div>
        </div>
        """
    )
    with st.container(border=True, key="scenario_info"):
        st.caption("ACTIVE DEMO SCENARIO")
        st.markdown("**One simulated division**")
        st.caption("3 sections · 12-hour planning horizon")
        status_color = "green" if result.status in {"OPTIMAL", "FEASIBLE"} else "orange"
        st.badge(result.status, icon=":material/check_circle:", color=status_color)
        st.caption("Current CP-SAT solver status")

    st.caption("SCENARIO CHANGE")
    train_names = data["trains"].set_index("train_id")["train_name"].to_dict()
    train_sections = data["trains"].set_index("train_id")["section_id"].to_dict()

    def format_train(train_id: str) -> str:
        if train_id == "None":
            return "No train cancellation"
        return f"{train_id} · {train_names[train_id]} · {train_sections[train_id]}"

    selected_train = st.selectbox(
        "Simulated train cancellation",
        ["None"] + data["trains"].train_id.tolist(),
        key="cancelled_train_selection",
        format_func=format_train,
        help="Select a simulated train path to remove, then apply re-planning.",
    )
    selected_cancelled = set() if selected_train == "None" else {selected_train}
    if selected_cancelled != st.session_state.cancelled:
        st.warning(
            "Scenario change staged. Apply re-planning to update the recommendation.",
            icon=":material/pending_actions:",
        )
    elif st.session_state.cancelled:
        st.success(
            f"Scenario applied · {selected_train} cancelled in simulation",
            icon=":material/check_circle:",
        )
    else:
        st.caption("Base scenario is currently applied.")

    st.button(
        "Re-plan scenario",
        type="primary",
        width="stretch",
        icon=":material/refresh:",
        on_click=apply_replan,
        key="replan_action",
    )
    st.button(
        "Reset base scenario",
        width="stretch",
        icon=":material/restart_alt:",
        on_click=reset_scenario,
        key="reset_action",
    )

    if st.session_state.reset_notice:
        st.toast("Base scenario restored", icon=":material/check_circle:")
        st.session_state.reset_notice = False

    if st.session_state.demo_reset_notice:
        st.toast("Demo reset — all session state restored to base scenario", icon=":material/restart_alt:")
        st.session_state.demo_reset_notice = False

    with st.container(border=True, key="safety_boundary"):
        st.markdown(":material/health_and_safety: **Prototype boundary**")
        st.caption(
            "Planning recommendation only. Human authorization and railway safety procedures remain mandatory."
        )

    st.caption("SIH DEMO MODE")
    st.toggle(
        "Guided demo walkthrough",
        key="demo_mode",
        help="Shows a step-by-step checklist on the Control Room tab, using only real values already computed from the existing demo dataset.",
    )

    st.caption("OFFICIAL TEAM")
    st.markdown("**Crafters** · Chandighar University")
    st.caption("Yash Nalandwar · Manpreet Kaur · Niraj Patil · Adarsh Kumar · Vishal Kumar · Arzoo")


render_header()
render_data_notice()

(
    overview,
    planning,
    ai_health,
    coordination,
    replanning,
    whatif,
    twin,
    analytics,
    planner,
    sih_demo,
    architecture,
    evidence,
    inputs,
    logic,
    limits,
) = st.tabs(
    [
        ":material/home: 🏠 Control Room",
        ":material/route: 📋 Block Optimizer",
        ":material/psychology_alt: 🧠 AI Asset Health",
        ":material/hub: 🔗 Coordination",
        ":material/bolt: 🚨 Re-planning",
        ":material/science: 🎮 What-If Simulation",
        ":material/map: 🗺️ Digital Twin",
        ":material/monitoring: 📊 Analytics",
        ":material/calendar_month: 📅 Planner",
        ":material/military_tech: 🏆 SIH Demo Mode",
        ":material/schema: 📐 Architecture",
        ":material/fact_check: 📋 SIH Evidence",
        ":material/database: Input data",
        ":material/account_tree: How it works",
        ":material/shield: Limits & integration",
    ]
)

with overview:
    render_section_heading(
        "RailBlock AI",
        "Railway Operations Control Room",
        "AI-Powered Railway Maintenance Block Optimization — demo / simulation mode.",
    )
    render_system_status_strip(result, st.session_state.demo_mode)

    with st.expander("System Status — engine readiness (this process, not an external connection)", icon=":material/monitor_heart:"):
        for check in system_status_checks:
            status_ok = check["status"] == "READY"
            st.markdown(
                f"{'✓' if status_ok else '✗'} **{check['component']}** — {check['status']}"
            )
        st.caption("Reflects this Streamlit process's own module initialization. No external railway system is connected.")

    if st.session_state.demo_mode:
        with st.container(border=True, key="demo_mode_panel"):
            st.markdown("#### :material/school: SIH Demo Walkthrough")
            st.caption("Every value below is read live from the actual demo dataset and current plan — nothing is scripted.")
            top_asset = risk_table.sort_values("risk_score", ascending=False).iloc[0] if not risk_table.empty else None
            demo_steps = [
                f"1. Critical asset identified — {top_asset.asset_id} ({top_asset.asset_name}) at risk {top_asset.risk_score}/100." if top_asset is not None else "1. No asset risk data available.",
                "2. Maintenance requests loaded from data/maintenance_requests.csv (see Input data tab).",
                f"3. AI risk calculated for all {len(risk_table)} assets (see AI Asset Health tab).",
                f"4. Coordination opportunities identified: {len(opportunities)} (see Coordination tab).",
                f"5. CP-SAT schedule generated — status {result.status}, {result.metrics['scheduled_requests']}/{result.metrics['total_requests']} scheduled.",
                "6. Recommendation explained per request (see Block Optimizer tab, 'Why was this recommended?').",
                "7. Controller reviews plan using Approve / Modify / Reject actions below.",
                "8. Introduce a train disruption in the 🚨 Re-planning tab.",
                "9. Explore a hypothetical scenario in the 🎮 What-If Simulation tab.",
                "10. Compare the re-optimized plan against the original (built into both tabs above).",
                f"11. Before vs after metrics: {len(baseline.conflicts)} baseline conflicts → {len(result.conflicts)} validator conflicts (see 📊 Analytics tab).",
            ]
            for step in demo_steps:
                st.markdown(f"- {step}")

    render_control_room_kpis(result, risk_table)

    render_section_heading("Digital railway view", "Network snapshot", "Schematic section-by-section status — full interactive view in the 🗺️ Digital Twin tab.")
    render_network_view(section_states, key_prefix="control_room", interactive=False)

    command_col, blocks_col = st.columns([1, 1], gap="large")
    with command_col:
        render_section_heading("AI operations", "🤖 AI Operations Command Center", "Top risk asset and recommended block, from the existing risk and explainability engines.")
        render_ai_command_center(risk_table, result, data)

        render_section_heading("Alerts", "🚨 Operational Alerts", "Generated only from actual conflicts, deferrals, risk levels and coordination data.")
        alerts = build_operational_alerts(result, risk_table, opportunities)
        render_alert_center(alerts)

    with blocks_col:
        render_section_heading("Active blocks", "Active Blocks Panel", "Every scheduled block in the current recommended plan, with controller review actions.")
        render_active_blocks_panel(result, risk_table)

        render_section_heading("Coordination", "🔗 Multi-Department Opportunities", "Same engine as the Coordination tab — see there for full detail.")
        render_coordination_widget(opportunities)

        render_section_heading("Disruption monitor", "🚨 Disruption Monitor", "Reflects the last disruption applied in the Re-planning tab, if any.")
        render_disruption_widget()

    render_section_heading("Recent events", "Recent Events (this session)", "Session-local activity only — not a persisted historical log.")
    events = []
    if st.session_state.cancelled:
        events.append(f"Simulated train cancellation applied: {next(iter(st.session_state.cancelled))}.")
    if st.session_state.get("replan_disruption_result"):
        events.append("A disruption was re-planned in the 🚨 Re-planning tab.")
    if st.session_state.get("whatif_simulation_result"):
        events.append("A what-if scenario was run in the 🎮 What-If Simulation tab.")
    if st.session_state.controller_decisions:
        events.append(f"{len(st.session_state.controller_decisions)} controller review action(s) recorded this session.")
    if events:
        for event in events:
            st.caption(f"• {event}")
    else:
        st.caption("No session activity yet — base scenario is active.")

with planning:
    render_section_heading(
        "Recommended possession plan",
        "Block plan",
        "Optimized maintenance blocks across the simulated sections and planning horizon.",
    )
    if st.session_state.replan_summary:
        render_replan_summary(st.session_state.replan_summary)

    scheduled = result.plan[result.plan.status == "Scheduled"].copy()
    if not scheduled.empty:
        scheduled = scheduled.merge(
            data["assets"][["asset_id", "asset_name"]], on="asset_id", how="left"
        )
        scheduled["Start"] = scheduled.start_min.map(hhmm)
        scheduled["End"] = scheduled.end_min.map(hhmm)
        scheduled["timeline_start"] = pd.to_datetime(DEMO_DATE) + pd.to_timedelta(
            scheduled.start_min, unit="m"
        )
        scheduled["timeline_end"] = pd.to_datetime(DEMO_DATE) + pd.to_timedelta(
            scheduled.end_min, unit="m"
        )
        scheduled["section_label"] = scheduled["section_id"].map(lambda value: f"Section {value}")

        st.html(
            """
            <div class="rb-panel-caption">
              <div><span class="material-symbols-rounded">calendar_month</span><strong>Possession timeline</strong></div>
              <span>Hover over a block for complete request details</span>
            </div>
            """
        )
        timeline = px.timeline(
            scheduled,
            x_start="timeline_start",
            x_end="timeline_end",
            y="section_label",
            color="department",
            text="request_id",
            custom_data=[
                "request_id",
                "asset_name",
                "asset_id",
                "work_type",
                "crew_id",
                "Start",
                "End",
                "priority",
                "disruption",
                "window_id",
            ],
            color_discrete_map=DEPARTMENT_COLORS,
            category_orders={"section_label": ["Section SEC-A", "Section SEC-B", "Section SEC-C"]},
        )
        timeline.update_traces(
            textposition="inside",
            insidetextanchor="middle",
            marker_line_color="rgba(255,255,255,0.28)",
            marker_line_width=1,
            hovertemplate=(
                "<b>%{customdata[0]} · %{customdata[3]}</b><br>"
                "Asset: %{customdata[1]} (%{customdata[2]})<br>"
                "Crew: %{customdata[4]}<br>"
                "Block: %{customdata[5]}–%{customdata[6]}<br>"
                "Priority: %{customdata[7]}<br>"
                "Weighted disruption: %{customdata[8]} min<br>"
                "Candidate window: %{customdata[9]}<extra></extra>"
            ),
        )
        timeline.update_yaxes(
            autorange="reversed",
            title=None,
            gridcolor="rgba(151,170,190,0.12)",
            tickfont=dict(size=13),
        )
        timeline.update_xaxes(
            title="Simulated planning horizon · HH:MM",
            tickformat="%H:%M",
            dtick=60 * 60 * 1000,
            gridcolor="rgba(151,170,190,0.14)",
            showline=True,
            linecolor="rgba(151,170,190,0.24)",
        )
        timeline.update_layout(
            height=430,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(10,24,36,0.38)",
            font=dict(color="#DCE8F2"),
            legend=dict(
                title="Maintenance department",
                orientation="h",
                yanchor="bottom",
                y=1.05,
                xanchor="left",
                x=0,
            ),
            margin=dict(l=20, r=20, t=62, b=40),
            bargap=0.34,
            hoverlabel=dict(bgcolor="#102333", font_color="#F4F8FB", bordercolor="#34506A"),
        )
        st.plotly_chart(
            timeline,
            width="stretch",
            config={"displaylogo": False, "scrollZoom": False, "responsive": True},
        )
        st.caption(
            "Blocks, train interactions and windows are derived only from deterministic simulated CSV inputs."
        )

        st.html(
            """
            <div class="rb-panel-caption rb-table-heading">
              <div><span class="material-symbols-rounded">table_rows</span><strong>Request schedule</strong></div>
              <span>Sorted by section and optimized start time</span>
            </div>
            """
        )
        plan_table = result.plan.merge(
            data["assets"][["asset_id", "asset_name"]], on="asset_id", how="left"
        ).copy()
        plan_table["Status"] = plan_table["status"].map(
            {"Scheduled": "● Scheduled", "Deferred": "○ Deferred"}
        )
        plan_table["Request"] = plan_table["request_id"]
        plan_table["Asset"] = plan_table.apply(
            lambda row: f"{row['asset_name']} · {row['asset_id']}", axis=1
        )
        plan_table["Work type"] = plan_table["work_type"]
        plan_table["Section"] = plan_table["section_id"]
        plan_table["Department"] = plan_table["department"]
        plan_table["Crew"] = plan_table["crew_id"]
        plan_table["Start"] = plan_table.apply(
            lambda row: hhmm(row.start_min) if row.status == "Scheduled" else "—", axis=1
        )
        plan_table["End"] = plan_table.apply(
            lambda row: hhmm(row.end_min) if row.status == "Scheduled" else "—", axis=1
        )
        plan_table["Duration"] = plan_table["duration_min"]
        plan_table["Priority"] = plan_table["priority"]
        plan_table["Disruption"] = plan_table["disruption"]
        display_columns = [
            "Status",
            "Request",
            "Asset",
            "Work type",
            "Section",
            "Department",
            "Crew",
            "Start",
            "End",
            "Duration",
            "Priority",
            "Disruption",
        ]
        st.dataframe(
            plan_table.sort_values(["section_id", "start_min"])[display_columns],
            hide_index=True,
            width="stretch",
            height=320,
            column_config={
                "Status": st.column_config.TextColumn(width="medium", pinned=True),
                "Request": st.column_config.TextColumn(width="small", pinned=True),
                "Asset": st.column_config.TextColumn(width="large"),
                "Work type": st.column_config.TextColumn(width="large"),
                "Section": st.column_config.TextColumn(width="small"),
                "Department": st.column_config.TextColumn(width="medium"),
                "Crew": st.column_config.TextColumn(width="small"),
                "Start": st.column_config.TextColumn(width="small"),
                "End": st.column_config.TextColumn(width="small"),
                "Duration": st.column_config.NumberColumn("Duration (min)", width="small"),
                "Priority": st.column_config.NumberColumn(width="small"),
                "Disruption": st.column_config.NumberColumn(
                    "Weighted disruption (min)", width="small"
                ),
            },
        )

    st.html(
        """
        <div class="rb-panel-caption rb-table-heading">
          <div><span class="material-symbols-rounded">psychology</span><strong>Why was this recommended?</strong></div>
          <span>AI Advisory — generated from the actual schedule, not a template</span>
        </div>
        """
    )
    explain_request_id = st.selectbox(
        "Inspect explanation for request",
        result.plan.request_id.tolist(),
        key="explain_request_selector",
    )
    explanation = explain_recommendation(explain_request_id, result, data["assets"])
    with st.container(border=True, key="explanation_panel"):
        st.markdown(f"**{explanation['headline']}**")
        for reason in explanation["reasons"]:
            st.markdown(f"- {reason}")

    deferred = result.plan[result.plan.status == "Deferred"]
    if not deferred.empty:
        st.warning(
            f"{len(deferred)} request(s) were deferred because no selected option improved the constrained objective.",
            icon=":material/schedule:",
        )

    with st.container(border=True, key="validator_panel"):
        st.markdown("#### :material/fact_check: Independent conflict validation")
        if result.conflicts:
            st.error(
                f"The independent validator detected {len(result.conflicts)} conflict(s).",
                icon=":material/error:",
            )
            st.dataframe(pd.DataFrame(result.conflicts), hide_index=True, width="stretch")
        else:
            st.success(
                "Conflict-free recommendation: no protected-train, request-window, section-capacity or crew conflicts detected.",
                icon=":material/verified:",
            )

with ai_health:
    render_section_heading(
        "AI Advisory — Prototype / Synthetic Data",
        "AI Asset Health",
        "Deterministic, explainable risk scoring over synthetic demo asset attributes.",
    )
    st.warning(
        "AI Advisory — Prototype / Synthetic Data. Risk scores come from a transparent rule-based "
        "formula over demo CSV columns (not a trained ML model) and never automatically change the "
        "manual request priority the optimizer uses.",
        icon=":material/psychology_alt:",
    )

    manual_priority = data["requests"].groupby("asset_id")["priority"].max()
    ai_health_table = risk_table.copy()
    ai_health_table["manual_priority"] = ai_health_table["asset_id"].map(manual_priority)
    ai_health_table = ai_health_table.sort_values("risk_score", ascending=False)

    for _, asset_risk in ai_health_table.iterrows():
        with st.container(border=True):
            header_col, badge_col = st.columns([3, 1])
            with header_col:
                st.markdown(f"**{asset_risk.asset_name}** · {asset_risk.asset_id} · {asset_risk.section_id}")
            with badge_col:
                st.badge(asset_risk.risk_level, color=RISK_BADGE_COLORS.get(asset_risk.risk_level, "gray"))
            st.progress(
                int(asset_risk.risk_score) / 100,
                text=f"Risk score: {asset_risk.risk_score}/100",
            )
            manual = asset_risk.manual_priority
            manual_label = "No pending request" if pd.isna(manual) else f"{int(manual)}/5"
            st.caption(
                f"Manual priority: {manual_label} · AI-suggested priority: {asset_risk.ai_suggested_priority}"
            )
            with st.expander("Why this score?", icon=":material/help:"):
                for factor in asset_risk.factors:
                    st.markdown(f"- {factor}")
                st.markdown(f"**Recommended action:** {asset_risk.recommended_action}")

    st.html(
        """
        <div class="rb-panel-caption rb-table-heading">
          <div><span class="material-symbols-rounded">rule</span><strong>AI Priority Approval</strong></div>
          <span>AI Recommendation → Controller Review Required → Controller Approved</span>
        </div>
        """
    )
    st.caption("AI priority will affect optimization only after approval and an explicit re-optimize action below.")
    for _, review_row in priority_review_table.sort_values("risk_score", ascending=False).iterrows():
        request_id = review_row.request_id
        approved_number = st.session_state.approved_priorities.get(request_id)
        with st.container(border=True):
            head_col, badge_col = st.columns([3, 1])
            with head_col:
                st.markdown(f"**{request_id}** · {review_row.work_type} · Asset {review_row.asset_id}")
            with badge_col:
                st.badge("AI Recommendation", color="blue")
            st.caption(
                f"Manual priority: {int(review_row.priority)}/5 · AI-suggested priority: "
                f"{review_row.ai_suggested_priority} ({review_row.ai_suggested_priority_number}/5, "
                f"risk {review_row.risk_score}/100)"
            )
            if approved_number is not None:
                st.success(
                    f"Controller Approved — priority {approved_number}/5 will be used once re-optimized.",
                    icon=":material/check_circle:",
                )
            action_cols = st.columns([1, 1, 3])
            if action_cols[0].button("Approve", key=f"approve_priority_{request_id}", icon=":material/check_circle:"):
                st.session_state.approved_priorities[request_id] = int(review_row.ai_suggested_priority_number)
                record_event(
                    st.session_state.audit_log,
                    "AI Recommendation Approved",
                    request_id,
                    f"Controller approved {review_row.ai_suggested_priority} priority "
                    f"({review_row.ai_suggested_priority_number}/5)",
                )
            if action_cols[1].button("Reject", key=f"reject_priority_{request_id}", icon=":material/cancel:"):
                st.session_state.approved_priorities.pop(request_id, None)
                record_event(
                    st.session_state.audit_log,
                    "AI Recommendation Rejected",
                    request_id,
                    "Controller rejected AI-suggested priority; manual priority remains",
                )
    st.html(
        '<div class="rb-controller-note">Prototype action — no external railway system is controlled.</div>'
    )

    if st.session_state.approved_priorities:
        st.markdown(f"**{len(st.session_state.approved_priorities)} approved priority override(s) pending re-optimization.**")
        if st.button(
            "Apply approved priorities and re-optimize",
            type="primary",
            icon=":material/bolt:",
            key="apply_approved_priorities_button",
        ):
            updated_requests = apply_approved_priorities(data["requests"], st.session_state.approved_priorities)
            priority_result = optimize_blocks(
                updated_requests, data["trains"], data["windows"], cancelled_train_ids=st.session_state.cancelled
            )
            priority_metrics = compute_all_metrics(
                priority_result.plan, priority_result.conflicts, updated_requests, risk_table, data["windows"], opportunities
            )
            st.session_state.priority_replan_result = {
                "result": priority_result,
                "comparison": compare_metrics(current_metrics, priority_metrics),
            }
            record_event(
                st.session_state.audit_log,
                "Schedule Generated",
                "Priority-approved plan",
                f"Re-optimized with {len(st.session_state.approved_priorities)} approved priority override(s)",
            )

    priority_replan_state = st.session_state.get("priority_replan_result")
    if priority_replan_state:
        with st.container(border=True, key="priority_replan_panel"):
            st.markdown("#### :material/bolt: Priority-Approved Re-optimization")
            st.caption(
                "This re-optimization used controller-approved AI priorities as an optimizer input. "
                "The live plan shown in Block Optimizer is unaffected unless you re-run it with the same override."
            )
            priority_comparison = priority_replan_state["comparison"]
            metric_cols = st.columns(4)
            metric_cols[0].metric(
                "Conflicts", priority_comparison["after"]["conflicts"],
                delta=priority_comparison["improvement"]["conflicts"], delta_color="inverse",
            )
            metric_cols[1].metric(
                "Deferred", priority_comparison["after"]["deferred_requests"],
                delta=priority_comparison["improvement"]["deferred_requests"], delta_color="inverse",
            )
            metric_cols[2].metric(
                "Train impact (min)", priority_comparison["after"]["train_impact_minutes"],
                delta=priority_comparison["improvement"]["train_impact_minutes"], delta_color="inverse",
            )
            metric_cols[3].metric(
                "Risk-weighted coverage %", priority_comparison["after"]["risk_weighted_maintenance_coverage_pct"],
                delta=priority_comparison["improvement"]["risk_weighted_maintenance_coverage_pct"],
            )

with coordination:
    render_section_heading(
        "AI Suggestion — Controller Approval Required",
        "🔗 Multi-Department Coordination",
        "Detects maintenance requests that could plausibly share one possession instead of running sequentially.",
    )
    st.warning(
        "AI-suggested coordination — controller approval required. Figures below are an estimated "
        "scheduling benefit only, not a measured real-world railway operational saving.",
        icon=":material/groups_2:",
    )

    summary_cols = st.columns(2)
    summary_cols[0].metric("Coordination opportunities found", opportunity_summary["opportunity_count"])
    summary_cols[1].metric(
        "Total estimated possession reduction", f"{opportunity_summary['total_estimated_reduction_minutes']} min"
    )

    if not opportunities:
        st.info(
            "No compatible coordination opportunities in the current demo dataset — remaining "
            "same-section requests share a crew, share a department, or their requested windows "
            "don't jointly fit inside one candidate window.",
            icon=":material/info:",
        )
    for group in opportunities:
        with st.container(border=True):
            st.markdown(f"**Potential Coordination Group · Section {group['section']}** ({group['group_id']})")
            for department in group["department_labels"]:
                st.markdown(f"- {department} ✓")
            st.caption(f"Requests: {', '.join(group['request_ids'])}")
            st.caption(
                f"Shared possession: {hhmm(group['shared_start_min'])}–{hhmm(group['shared_end_min'])}"
            )
            savings_cols = st.columns(3)
            savings_cols[0].metric("Current separate possession", f"{group['individual_duration_minutes']} min")
            savings_cols[1].metric("Coordinated possession", f"{group['combined_duration_minutes']} min")
            savings_cols[2].metric(
                "Estimated reduction", f"{group['estimated_possession_reduction_minutes']} min"
            )
            st.caption(group["reason"])
            st.warning("AI-suggested coordination — controller approval required.", icon=":material/verified_user:")

            coordination_key = f"coordination:{group['group_id']}"
            decision = st.session_state.controller_decisions.get(coordination_key)
            action_cols = st.columns([1, 1, 3])
            if action_cols[0].button("Approve", key=f"approve_{coordination_key}", icon=":material/check_circle:"):
                st.session_state.controller_decisions[coordination_key] = "APPROVED"
                st.session_state.coordination_proposals[group["group_id"]] = build_optimization_proposal(
                    group, data["requests"]
                )
                record_event(
                    st.session_state.audit_log,
                    "Coordination Approved",
                    group["group_id"],
                    f"Controller approved coordination of {', '.join(group['request_ids'])}",
                )
            if action_cols[1].button("Reject", key=f"reject_{coordination_key}", icon=":material/cancel:"):
                st.session_state.controller_decisions[coordination_key] = "REJECTED"
                st.session_state.coordination_proposals.pop(group["group_id"], None)
                record_event(
                    st.session_state.audit_log,
                    "Coordination Rejected",
                    group["group_id"],
                    "Controller rejected the suggested coordination group",
                )
            with action_cols[2]:
                if decision:
                    st.badge(decision, color={"APPROVED": "green", "REJECTED": "red"}.get(decision, "gray"))

            proposal = st.session_state.coordination_proposals.get(group["group_id"])
            if proposal:
                with st.container(border=True):
                    st.markdown("**Optimization Proposal**")
                    st.caption(
                        f"Crews involved: {', '.join(proposal['crews_involved'])} · "
                        f"Shared possession {hhmm(proposal['shared_start_min'])}–{hhmm(proposal['shared_end_min'])}"
                    )
                    st.warning(proposal["status"], icon=":material/engineering:")
            st.html(
                '<div class="rb-controller-note">Prototype action — no external railway system is controlled.</div>'
            )

with replanning:
    render_section_heading(
        "AI Recommendation — Controller Review Required",
        "🚨 Dynamic Re-planning",
        "Apply a disruption to the current plan and re-optimize with the same CP-SAT engine used everywhere else in RailBlock AI.",
    )
    st.caption("Current Plan → Disruption → Update state → Same CP-SAT optimizer → Re-optimized plan → Validation")

    disruption_kind = st.selectbox(
        "Disruption type",
        ["Train delay", "Block unavailable", "Emergency maintenance"],
        key="disruption_kind_selector",
    )
    if disruption_kind == "Train delay":
        disruption_train = st.selectbox(
            "Train", data["trains"].train_id.tolist(), format_func=format_train, key="disruption_train_selector"
        )
        disruption_delay = st.slider("Delay (minutes)", 5, 120, 20, step=5, key="disruption_delay_slider")
        pending_disruption = {"type": "TRAIN_DELAY", "train_id": disruption_train, "delay_minutes": disruption_delay}
        st.caption(f"🚨 TRAIN {disruption_train} DELAYED BY {disruption_delay} MINUTES")
    elif disruption_kind == "Block unavailable":
        disruption_window = st.selectbox(
            "Candidate window", data["windows"].window_id.tolist(), key="disruption_window_selector"
        )
        pending_disruption = {"type": "BLOCK_UNAVAILABLE", "window_id": disruption_window}
        st.caption(f"🚨 CANDIDATE WINDOW {disruption_window} BECOMES UNAVAILABLE")
    else:
        disruption_section = st.selectbox(
            "Section", sorted(data["windows"].section_id.unique()), key="disruption_section_selector"
        )
        disruption_duration = st.slider("Duration (minutes)", 15, 180, 60, step=15, key="disruption_duration_slider")
        pending_disruption = {
            "type": "EMERGENCY_MAINTENANCE",
            "request": {
                "request_id": "MR-EMERGENCY",
                "asset_id": data["assets"][data["assets"].section_id == disruption_section].asset_id.iloc[0],
                "work_type": "Emergency inspection",
                "section_id": disruption_section,
                "department": "Engineering",
                "duration_min": disruption_duration,
                "priority": 5,
                "earliest_start": 0,
                "latest_end": 780,
                "crew_id": data["resources"][data["resources"].department == "Engineering"].crew_id.iloc[0],
            },
        }
        st.caption(f"🚨 EMERGENCY MAINTENANCE REQUESTED — SECTION {disruption_section}")

    if st.button("Re-plan with disruption", type="primary", icon=":material/bolt:", key="run_replan_button"):
        st.session_state.replan_disruption_result = replan_after_disruption(
            data["requests"], data["trains"], data["windows"], pending_disruption, baseline_result=result
        )

    replan_disruption_result = st.session_state.get("replan_disruption_result")
    if replan_disruption_result:
        comparison = replan_disruption_result.comparison
        metric_cols = st.columns(3)
        metric_cols[0].metric(
            "Conflicts", comparison["after"]["conflicts"],
            delta=comparison["improvement"]["conflicts"], delta_color="inverse",
        )
        metric_cols[1].metric(
            "Deferred", comparison["after"]["deferred_requests"],
            delta=comparison["improvement"]["deferred_requests"], delta_color="inverse",
        )
        metric_cols[2].metric(
            "Train impact (min)", comparison["after"]["train_impact_minutes"],
            delta=comparison["improvement"]["train_impact_minutes"], delta_color="inverse",
        )

        replan_diff = compare_plans(
            plan_snapshot(replan_disruption_result.baseline_result.plan), replan_disruption_result.result.plan
        )
        st.markdown("**[ VIEW CHANGES ]**")
        if not replan_diff.empty:
            st.dataframe(replan_diff, hide_index=True, width="stretch")
            replan_explain_id = st.selectbox(
                "Explain a changed request", replan_diff["Request"].tolist(), key="replan_explain_selector"
            )
            replan_explanation = explain_recommendation(
                replan_explain_id, replan_disruption_result.result, data["assets"]
            )
            with st.container(border=True):
                st.markdown(f"**{replan_explanation['headline']}**")
                for reason in replan_explanation["reasons"]:
                    st.markdown(f"- {reason}")
        else:
            st.info("This disruption did not change the recommended schedule.", icon=":material/info:")

        if replan_disruption_result.result.conflicts:
            st.error(
                f"✗ {len(replan_disruption_result.result.conflicts)} conflict(s) remain — controller review required before publishing.",
                icon=":material/error:",
            )
        else:
            st.success(
                "✓ No protected-train conflict · ✓ All maintenance constraints satisfied (independent validator).",
                icon=":material/verified:",
            )
        st.caption("AI Recommendation — Controller Review Required. Simulation Result / Prototype / Synthetic Data.")

with whatif:
    render_section_heading(
        "Simulation Result — Prototype / Synthetic Data",
        "🎮 What-If Simulation",
        "Test a hypothetical disruption on a temporary copy of the plan. The live schedule above is never changed.",
    )
    st.caption(
        "Original state → temporary copy → apply scenario → same CP-SAT optimizer → validate → compare → discard temporary state."
    )

    whatif_scenario_type = st.radio(
        "Scenario type",
        ["Train Delay", "Block Unavailable", "Emergency Maintenance", "Duration Increase"],
        horizontal=True,
        key="whatif_scenario_type_radio",
    )

    if whatif_scenario_type == "Train Delay":
        whatif_train = st.selectbox(
            "Train", data["trains"].train_id.tolist(), format_func=format_train, key="whatif_train_selector"
        )
        whatif_delay = st.slider("Delay (minutes)", 5, 120, 20, step=5, key="whatif_delay_slider")
        whatif_scenario = {"type": "TRAIN_DELAY", "train_id": whatif_train, "delay_minutes": whatif_delay}
    elif whatif_scenario_type == "Block Unavailable":
        whatif_window = st.selectbox(
            "Candidate window", data["windows"].window_id.tolist(), key="whatif_window_selector"
        )
        whatif_scenario = {"type": "BLOCK_UNAVAILABLE", "window_id": whatif_window}
    elif whatif_scenario_type == "Emergency Maintenance":
        whatif_section = st.selectbox(
            "Section", sorted(data["windows"].section_id.unique()), key="whatif_section_selector"
        )
        whatif_duration = st.slider("Duration (minutes)", 15, 180, 60, step=15, key="whatif_emergency_duration_slider")
        whatif_scenario = {
            "type": "EMERGENCY_MAINTENANCE",
            "request": {
                "request_id": "MR-WHATIF-EMERGENCY",
                "asset_id": data["assets"][data["assets"].section_id == whatif_section].asset_id.iloc[0],
                "work_type": "Emergency inspection",
                "section_id": whatif_section,
                "department": "Engineering",
                "duration_min": whatif_duration,
                "priority": 5,
                "earliest_start": 0,
                "latest_end": 780,
                "crew_id": data["resources"][data["resources"].department == "Engineering"].crew_id.iloc[0],
            },
        }
    else:
        whatif_request = st.selectbox("Request", data["requests"].request_id.tolist(), key="whatif_duration_request_selector")
        whatif_extra = st.slider("Additional minutes", 15, 120, 30, step=15, key="whatif_extra_minutes_slider")
        whatif_scenario = {"type": "DURATION_INCREASE", "request_id": whatif_request, "additional_minutes": whatif_extra}

    if st.button("RUN SIMULATION", type="primary", icon=":material/play_circle:", key="run_whatif_button"):
        st.session_state.whatif_simulation_result = run_what_if_scenario(
            data["requests"], data["trains"], data["windows"], whatif_scenario, current_result=result
        )

    whatif_simulation_result = st.session_state.get("whatif_simulation_result")
    if whatif_simulation_result:
        current_res = whatif_simulation_result.current_result
        simulated_res = whatif_simulation_result.simulated_result

        current_col, simulated_col = st.columns(2)
        with current_col:
            st.markdown("**CURRENT**")
            st.caption(
                f"{current_res.metrics['scheduled_requests']}/{current_res.metrics['total_requests']} scheduled "
                f"· {len(current_res.conflicts)} conflict(s)"
            )
        with simulated_col:
            st.markdown("**SIMULATED**")
            st.caption(
                f"{simulated_res.metrics['scheduled_requests']}/{simulated_res.metrics['total_requests']} scheduled "
                f"· {len(simulated_res.conflicts)} conflict(s)"
            )

        whatif_comparison = whatif_simulation_result.comparison
        whatif_metric_cols = st.columns(4)
        whatif_metric_cols[0].metric(
            "Conflicts", whatif_comparison["after"]["conflicts"],
            delta=whatif_comparison["improvement"]["conflicts"], delta_color="inverse",
        )
        whatif_metric_cols[1].metric(
            "Train impact (min)", whatif_comparison["after"]["train_impact_minutes"],
            delta=whatif_comparison["improvement"]["train_impact_minutes"], delta_color="inverse",
        )
        whatif_metric_cols[2].metric(
            "Deferred jobs", whatif_comparison["after"]["deferred_requests"],
            delta=whatif_comparison["improvement"]["deferred_requests"], delta_color="inverse",
        )
        whatif_metric_cols[3].metric(
            "Possession minutes", whatif_comparison["after"]["total_block_duration_minutes"],
            delta=whatif_comparison["improvement"]["total_block_duration_minutes"],
        )

        whatif_diff = compare_plans(plan_snapshot(current_res.plan), simulated_res.plan)
        if not whatif_diff.empty:
            st.dataframe(whatif_diff, hide_index=True, width="stretch")
            st.markdown("**Why did the schedule change?**")
            whatif_explain_id = st.selectbox(
                "Inspect a changed request", whatif_diff["Request"].tolist(), key="whatif_explain_selector"
            )
            whatif_explanation = explain_recommendation(whatif_explain_id, simulated_res, data["assets"])
            with st.container(border=True):
                st.markdown(f"**{whatif_explanation['headline']}**")
                for reason in whatif_explanation["reasons"]:
                    st.markdown(f"- {reason}")
        else:
            st.info("This simulated scenario did not change the recommended schedule.", icon=":material/info:")

        st.caption(
            "Simulation Result — Prototype / Synthetic Data. The live schedule shown in Block plan was not modified."
        )

with twin:
    render_section_heading(
        "Visualization / Simulation Layer — Not Live Railway Infrastructure",
        "🗺️ Digital Twin",
        "A schematic view of sections, blocks, train windows and risk, built only from data already computed elsewhere in this app.",
    )
    st.warning(
        "The Digital Twin is a visualization and simulation layer over synthetic/demo data. It is not a "
        "live representation of railway infrastructure — sections are placed schematically, and every "
        "train shown is at its scheduled/simulated time window, never a real-time position.",
        icon=":material/map:",
    )
    render_network_view(section_states, key_prefix="twin_tab", interactive=True)

with analytics:
    render_section_heading(
        "Decision impact",
        "📊 Analytics",
        "Before vs after metrics and distributions computed only from the current plan, baseline and risk table.",
    )
    render_kpis(result, baseline)
    render_before_after(result, baseline)

    render_section_heading(
        "Advanced KPI engine",
        "Baseline vs Optimized",
        "All 12 metrics from railblock/metrics.py, computed once and reused everywhere they're shown.",
    )
    render_metrics_comparison_table(compare_metrics(baseline_metrics, current_metrics), "Baseline", "Optimized")

    disruption_state = st.session_state.get("replan_disruption_result")
    if disruption_state:
        render_section_heading(
            "Advanced KPI engine",
            "Baseline vs Disruption Re-plan",
            "The most recent disruption applied in the 🚨 Re-planning tab, compared against the naive baseline.",
        )
        disruption_metrics = compute_all_metrics(
            disruption_state.result.plan,
            disruption_state.result.conflicts,
            disruption_state.disrupted_requests,
            risk_table,
            disruption_state.disrupted_windows,
            opportunities,
        )
        render_metrics_comparison_table(
            compare_metrics(baseline_metrics, disruption_metrics), "Baseline", "Disruption Re-plan"
        )

    with st.expander("Inspect conflict comparison chart", icon=":material/bar_chart:"):
        conflict_comparison = pd.DataFrame(
            {
                "Plan": ["Naive baseline", "Optimized recommendation"],
                "Detected conflicts": [len(baseline.conflicts), len(result.conflicts)],
                "Scheduled requests": [len(baseline.plan), result.metrics["scheduled_requests"]],
            }
        )
        conflict_chart = px.bar(
            conflict_comparison,
            x="Plan",
            y="Detected conflicts",
            color="Plan",
            text_auto=True,
            color_discrete_sequence=["#F97366", "#2DD4A8"],
        )
        conflict_chart.update_layout(
            height=320,
            showlegend=False,
            margin=dict(l=20, r=20, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title=None,
            yaxis_title="Validator conflicts",
            font=dict(color="#DCE8F2"),
        )
        conflict_chart.update_yaxes(gridcolor="rgba(151,170,190,0.16)", rangemode="tozero")
        st.plotly_chart(conflict_chart, width="stretch", config={"displayModeBar": False}, key="analytics_conflict_chart")

    chart_col_a, chart_col_b = st.columns(2, gap="large")
    with chart_col_a:
        st.markdown("**Risk distribution**")
        risk_counts = risk_table["risk_level"].value_counts().reindex(["LOW", "MEDIUM", "HIGH", "CRITICAL"]).fillna(0)
        risk_chart = px.bar(
            x=risk_counts.index,
            y=risk_counts.values,
            color=risk_counts.index,
            color_discrete_map={"LOW": "#2DD4A8", "MEDIUM": "#4C9AFF", "HIGH": "#F5B942", "CRITICAL": "#F97366"},
            labels={"x": "Risk level", "y": "Asset count"},
        )
        risk_chart.update_layout(
            height=300, showlegend=False, margin=dict(l=20, r=20, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#DCE8F2"),
        )
        st.plotly_chart(risk_chart, width="stretch", config={"displayModeBar": False}, key="analytics_risk_chart")

        st.markdown("**Block utilization**")
        st.progress(
            min(1.0, result.metrics["block_utilization_pct"] / 100),
            text=f"{result.metrics['block_utilization_pct']}% of total candidate-window minutes used",
        )

    with chart_col_b:
        st.markdown("**Maintenance priority distribution**")
        priority_counts = data["requests"]["priority"].value_counts().sort_index()
        priority_chart = px.bar(
            x=priority_counts.index.astype(str),
            y=priority_counts.values,
            labels={"x": "Manual priority (1-5)", "y": "Request count"},
            color_discrete_sequence=["#A78BFA"],
        )
        priority_chart.update_layout(
            height=300, showlegend=False, margin=dict(l=20, r=20, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#DCE8F2"),
        )
        st.plotly_chart(priority_chart, width="stretch", config={"displayModeBar": False}, key="analytics_priority_chart")

        st.markdown("**Train impact by request (weighted disruption minutes)**")
        impact_source = result.plan[result.plan.status == "Scheduled"]
        if not impact_source.empty:
            impact_chart = px.bar(
                impact_source.sort_values("disruption", ascending=False),
                x="request_id",
                y="disruption",
                labels={"request_id": "Request", "disruption": "Weighted disruption (min)"},
                color_discrete_sequence=["#F97366"],
            )
            impact_chart.update_layout(
                height=300, showlegend=False, margin=dict(l=20, r=20, t=20, b=20),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#DCE8F2"),
            )
            st.plotly_chart(impact_chart, width="stretch", config={"displayModeBar": False}, key="analytics_impact_chart")
        else:
            st.info("No scheduled blocks to chart in the current plan.", icon=":material/info:")

with planner:
    render_section_heading(
        "Visualization Around Existing Scheduling",
        "📅 Weekly Planner",
        "A lightweight weekly view built around the existing single-day optimizer — not a new multi-day optimization algorithm.",
    )
    st.info(
        "This demo dataset covers one simulated day. Only the first day below uses a real CP-SAT-computed "
        "schedule; the remaining days are explicitly placeholders, not fabricated data. Multi-day rolling-horizon "
        "planning is documented future work (see docs/ALGORITHM.md).",
        icon=":material/info:",
    )

    weekday_labels = ["Day 1 (demo date)", "Day 2", "Day 3", "Day 4", "Day 5", "Day 6", "Day 7"]
    planner_tabs = st.tabs(weekday_labels)

    with planner_tabs[0]:
        day_plan = result.plan.merge(
            data["assets"][["asset_id", "asset_name"]], on="asset_id", how="left"
        ).copy()
        risk_by_asset_planner = risk_table.set_index("asset_id")["risk_level"].to_dict()
        day_plan["Risk"] = day_plan["asset_id"].map(risk_by_asset_planner).fillna("N/A")
        day_plan["Status"] = day_plan["status"]
        day_plan["Start"] = day_plan.apply(lambda row: hhmm(row.start_min) if row.status == "Scheduled" else "—", axis=1)
        day_plan["End"] = day_plan.apply(lambda row: hhmm(row.end_min) if row.status == "Scheduled" else "—", axis=1)
        st.dataframe(
            day_plan[["request_id", "section_id", "department", "Status", "Start", "End", "Risk"]].rename(
                columns={"request_id": "Request", "section_id": "Section", "department": "Department"}
            ).sort_values(["Section", "Request"]),
            hide_index=True,
            width="stretch",
        )
    for empty_tab in planner_tabs[1:]:
        with empty_tab:
            st.caption("Not yet scheduled — this demo dataset contains only one simulated day.")

with sih_demo:
    render_section_heading(
        "Presenter Walkthrough — Prototype / Synthetic Data",
        "🏆 SIH Demo Mode",
        "The complete decision-support story, step by step, using only the real demo dataset and the functions already wired into every other tab.",
    )
    st.button(
        "🔄 RESET DEMO",
        type="primary",
        icon=":material/restart_alt:",
        on_click=reset_demo_state,
        key="reset_demo_button",
    )
    st.caption(
        "Restores session state (approvals, disruptions, simulations, audit log) to the base scenario. "
        "Source CSV files are never modified — they are only ever read."
    )

    demo_top_asset = risk_table.sort_values("risk_score", ascending=False).iloc[0]
    demo_requests = data["requests"][data["requests"].asset_id == demo_top_asset.asset_id]
    demo_request_id = demo_requests.request_id.iloc[0] if not demo_requests.empty else result.plan.request_id.iloc[0]

    with st.container(border=True):
        st.markdown("**STEP 1 · Asset Health**")
        st.markdown(
            f"Asset **{demo_top_asset.asset_id}** ({demo_top_asset.asset_name}) — "
            f"**{demo_top_asset.risk_level}** — {demo_top_asset.risk_score}/100"
        )

    with st.container(border=True):
        st.markdown("**STEP 2 · Maintenance Request**")
        if not demo_requests.empty:
            demo_request_row = demo_requests.iloc[0]
            st.markdown(
                f"**{demo_request_row.request_id}** · {demo_request_row.work_type} · "
                f"Section {demo_request_row.section_id} · Department {demo_request_row.department}"
            )
        else:
            st.caption("No pending maintenance request for this asset in the current demo dataset.")

    with st.container(border=True):
        st.markdown("**STEP 3 · AI Recommendation**")
        demo_review_row = priority_review_table[priority_review_table.request_id == demo_request_id]
        if not demo_review_row.empty:
            demo_review_row = demo_review_row.iloc[0]
            st.caption(
                f"Manual priority: {int(demo_review_row.priority)}/5 · AI-suggested: "
                f"{demo_review_row.ai_suggested_priority} ({demo_review_row.ai_suggested_priority_number}/5)"
            )
            st.caption("Approve/Reject this recommendation in the 🧠 AI Asset Health tab (AI Priority Approval).")

    with st.container(border=True):
        st.markdown("**STEP 4 · Coordination Opportunity**")
        if opportunities:
            demo_group = opportunities[0]
            st.markdown(
                f"Section {demo_group['section']}: {', '.join(demo_group['department_labels'])} — "
                f"estimated reduction {demo_group['estimated_possession_reduction_minutes']} min"
            )
            st.caption("Approve this group in the 🔗 Coordination tab to see the Optimization Proposal.")
        else:
            st.caption("No coordination opportunity in the current demo dataset.")

    with st.container(border=True):
        st.markdown("**STEP 5 · Generate Optimized Block**")
        st.markdown(
            f"CP-SAT status **{result.status}** · {result.metrics['scheduled_requests']}/{result.metrics['total_requests']} scheduled "
            f"· {len(result.conflicts)} conflict(s)"
        )

    with st.container(border=True):
        st.markdown("**STEP 6 · Explain Recommendation**")
        demo_explanation = explain_recommendation(demo_request_id, result, data["assets"])
        st.markdown(f"**{demo_explanation['headline']}**")
        for reason in demo_explanation["reasons"]:
            st.markdown(f"- {reason}")

    with st.container(border=True):
        st.markdown("**STEP 7 · Controller Approval**")
        render_controller_actions(f"demo:{demo_request_id}")

    with st.container(border=True):
        st.markdown("**STEP 8 · Introduce Disruption**")
        st.caption("Simulated: Train TR-101 delayed +20 minutes.")
        if st.button("Introduce Disruption", icon=":material/bolt:", key="demo_introduce_disruption"):
            st.session_state.replan_disruption_result = replan_after_disruption(
                data["requests"], data["trains"], data["windows"],
                {"type": "TRAIN_DELAY", "train_id": "TR-101", "delay_minutes": 20},
                baseline_result=result,
            )
            record_event(
                st.session_state.audit_log, "Disruption Introduced", "TR-101",
                "SIH Demo Mode: simulated +20 min train delay",
            )
        demo_disruption_state = st.session_state.get("replan_disruption_result")
        if demo_disruption_state:
            st.success(f"Disruption applied · {len(demo_disruption_state.result.conflicts)} conflict(s) in re-plan.", icon=":material/check_circle:")

    with st.container(border=True):
        st.markdown("**STEP 9 · Run What-If Simulation**")
        st.caption("Simulated: candidate window W-A1 becomes unavailable.")
        if st.button("Run What-If", icon=":material/play_circle:", key="demo_run_whatif"):
            st.session_state.whatif_simulation_result = run_what_if_scenario(
                data["requests"], data["trains"], data["windows"],
                {"type": "BLOCK_UNAVAILABLE", "window_id": "W-A1"},
                current_result=result,
            )
            record_event(
                st.session_state.audit_log, "Simulation Executed", "W-A1",
                "SIH Demo Mode: simulated candidate window unavailability",
            )
        demo_whatif_state = st.session_state.get("whatif_simulation_result")
        if demo_whatif_state:
            st.success(
                f"Simulation complete · {len(demo_whatif_state.simulated_result.conflicts)} conflict(s) in simulated plan.",
                icon=":material/check_circle:",
            )

    with st.container(border=True):
        st.markdown("**STEP 10 · Dynamic Re-planning**")
        render_disruption_widget()

    with st.container(border=True):
        st.markdown("**STEP 11 · Before vs After**")
        render_metrics_comparison_table(compare_metrics(baseline_metrics, current_metrics), "Baseline", "Optimized")

    if st.session_state.audit_log:
        with st.expander(f"🧾 Audit Trail ({len(st.session_state.audit_log)} event(s))", icon=":material/receipt_long:"):
            st.caption("Prototype audit trail for this session only — not a regulatory-compliance record.")
            for event in reversed(st.session_state.audit_log):
                st.caption(format_event(event))

with architecture:
    render_section_heading(
        "System Design",
        "📐 Architecture",
        "AI predicts and prioritizes. CP-SAT optimizes. Validation checks feasibility. The controller approves.",
    )
    architecture_steps = [
        ("dataset", "Data"),
        ("psychology_alt", "AI Asset Risk"),
        ("low_priority", "Maintenance Priority"),
        ("hub", "Multi-Department Coordination"),
        ("calculate", "CP-SAT Optimization"),
        ("fact_check", "Conflict Validation"),
        ("psychology", "Explainable Recommendation"),
        ("approval", "Controller Review"),
        ("check_circle", "Approved Plan"),
        ("bolt", "Disruption / What-If"),
        ("refresh", "Dynamic Re-planning"),
        ("map", "Digital Twin"),
        ("monitoring", "Analytics"),
    ]
    architecture_html = "".join(
        f"""
        <div class="rb-pipeline-step"><span class="material-symbols-rounded">{icon}</span><strong>{escape(label)}</strong></div>
        {'' if index == len(architecture_steps) - 1 else '<span class="rb-pipeline-arrow material-symbols-rounded">arrow_forward</span>'}
        """
        for index, (icon, label) in enumerate(architecture_steps)
    )
    st.html(f'<div class="rb-pipeline">{architecture_html}</div>')

    role_cols = st.columns(4, gap="medium")
    with role_cols[0]:
        with st.container(border=True, height="stretch"):
            st.markdown("#### :material/psychology_alt: AI predicts/prioritizes")
            st.caption(
                "railblock/risk.py scores assets and suggests a priority. Advisory only — never written "
                "to the manual priority column without explicit controller approval (railblock/approval.py)."
            )
    with role_cols[1]:
        with st.container(border=True, height="stretch"):
            st.markdown("#### :material/calculate: CP-SAT optimizes")
            st.caption(
                "railblock/optimizer.py's optimize_blocks() is the single scheduling engine used by every "
                "tab in this app — Block Optimizer, Re-planning, What-If, and Demo Mode alike."
            )
    with role_cols[2]:
        with st.container(border=True, height="stretch"):
            st.markdown("#### :material/fact_check: Validation checks feasibility")
            st.caption(
                "railblock/validation.py independently recomputes conflicts after every solve — it is never "
                "modified by, or made aware of, any AI or coordination decision."
            )
    with role_cols[3]:
        with st.container(border=True, height="stretch"):
            st.markdown("#### :material/approval: Controller approves")
            st.caption(
                "Every AI suggestion (priority, coordination) and every disruption/what-if outcome is labeled "
                "'Controller Review Required' with session-state-only Approve/Modify/Reject actions."
            )

    st.info(
        "Multi-department coordination (Engineering + S&T + Traction) is detected and can be approved as an "
        "Optimization Proposal, but true joint-block CP-SAT scheduling is documented future work — see "
        "docs/ALGORITHM.md ('Phase 4') for why it was not forced into the optimizer this phase.",
        icon=":material/hub:",
    )

with evidence:
    render_section_heading(
        "Prototype Demonstration",
        "📋 SIH Evidence",
        "A judge-facing summary of what is implemented, grounded in the same functions used throughout this app.",
    )
    evidence_cols = st.columns(2, gap="large")
    with evidence_cols[0]:
        with st.container(border=True, height="stretch"):
            st.markdown("#### :material/flag: Problem solved")
            st.markdown(
                "Coordinating railway maintenance blocks with train operations across Engineering, S&T and "
                "Traction departments while maximizing asset availability (SIH26027)."
            )
        with st.container(border=True, height="stretch"):
            st.markdown("#### :material/psychology_alt: AI component")
            st.markdown(
                "Transparent, rule-based asset risk scoring (railblock/risk.py) — prototype demonstration over "
                "synthetic data, not a trained ML model."
            )
        with st.container(border=True, height="stretch"):
            st.markdown("#### :material/science: Simulation component")
            st.markdown(
                "What-if scenarios and disruption re-planning (railblock/scenarios.py, railblock/disruptions.py) "
                "run on temporary copies — the live schedule is never altered by a simulation."
            )
        with st.container(border=True, height="stretch"):
            st.markdown("#### :material/groups: Controller-in-the-loop")
            st.markdown(
                "Every AI/coordination suggestion requires an explicit Approve/Modify/Reject action, recorded "
                "in a session-scoped audit trail (railblock/audit.py)."
            )
    with evidence_cols[1]:
        with st.container(border=True, height="stretch"):
            st.markdown("#### :material/auto_awesome: Technical novelty")
            st.markdown(
                "An independent validator that never trusts the optimizer's own conflict-freedom claim; "
                "advisory coordination detection kept deliberately separate from CP-SAT scheduling once "
                "found to require compromising that independence (see 📐 Architecture)."
            )
        with st.container(border=True, height="stretch"):
            st.markdown("#### :material/calculate: Optimization component")
            st.markdown(
                "Google OR-Tools CP-SAT constraint programming (railblock/optimizer.py) — the single scheduling "
                "engine behind every tab in this app."
            )
        with st.container(border=True, height="stretch"):
            st.markdown("#### :material/explore: Explainability")
            st.markdown(
                "Every scheduled or deferred request has a natural-language explanation generated from the "
                "actual candidate options the solver evaluated (railblock/explain.py) — never a template."
            )
        with st.container(border=True, height="stretch"):
            st.markdown("#### :material/trending_up: Expected operational benefit")
            st.markdown(
                f"**Estimated** — in this run: {opportunity_summary['total_estimated_reduction_minutes']} "
                "min estimated possession reduction from coordination, "
                f"{len(baseline.conflicts)} → {len(result.conflicts)} conflicts vs the naive baseline. "
                "Prototype demonstration only; not a measured real-world outcome."
            )

    st.warning(
        "All figures on this page are Prototype demonstration / Estimated / Simulation results over synthetic "
        "data. No real Indian Railways operational data, live connectivity, or field-measured impact is claimed.",
        icon=":material/health_and_safety:",
    )

with inputs:
    render_section_heading(
        "Transparent demo inputs",
        "Input data",
        "Inspect every deterministic simulated table used by the optimizer and validator.",
    )
    st.info(
        "These datasets are read-only in the dashboard and editable only through the repository CSV files.",
        icon=":material/info:",
    )

    with st.container(border=True, key="data_quality_panel"):
        st.markdown("#### :material/verified: Data Quality")
        st.badge(quality_report["data_mode"], color="orange", icon=":material/science:")
        count_cols = st.columns(len(quality_report["record_counts"]))
        for col, (name, count) in zip(count_cols, quality_report["record_counts"].items()):
            col.metric(name.capitalize(), count)
        missing_total = sum(quality_report["missing_values"].values())
        st.caption(
            f"Missing values across all loaded tables: {missing_total}"
            + (" (none)" if missing_total == 0 else "")
        )
        st.markdown("**Optional risk factors** (used by the AI risk engine if present):")
        for label, present in quality_report["optional_risk_columns"].items():
            st.markdown(f"- {label} {'✓' if present else '—'}")
        st.caption("Last data refresh: this Streamlit session's process start (cached via `st.cache_data`).")

    input_tables = [
        ("Assets", "assets", ":material/precision_manufacturing:"),
        ("Maintenance requests", "requests", ":material/construction:"),
        ("Train paths", "trains", ":material/train:"),
        ("Candidate windows", "windows", ":material/date_range:"),
        ("Crews", "resources", ":material/groups:"),
    ]
    for title, key, icon in input_tables:
        with st.expander(
            f"{title} · {len(data[key])} records",
            expanded=key == "requests",
            icon=icon,
        ):
            st.dataframe(data[key], hide_index=True, width="stretch")

with logic:
    render_section_heading(
        "Explainable decision pipeline",
        "How it works",
        "Optimization, railway rules and validation remain separate and auditable.",
    )
    pipeline_steps = [
        ("psychology_alt", "AI risk"),
        ("construction", "Maintenance requests"),
        ("hub", "Coordination"),
        ("calculate", "CP-SAT optimization"),
        ("fact_check", "Validation"),
        ("psychology", "Explainability"),
        ("approval", "Controller review"),
        ("bolt", "Dynamic re-planning"),
        ("science", "What-if simulation"),
        ("map", "Digital twin / control room"),
        ("monitoring", "Analytics"),
    ]
    pipeline_html = "".join(
        f"""
        <div class="rb-pipeline-step"><span class="material-symbols-rounded">{icon}</span><strong>{escape(label)}</strong></div>
        {'' if index == len(pipeline_steps) - 1 else '<span class="rb-pipeline-arrow material-symbols-rounded">arrow_forward</span>'}
        """
        for index, (icon, label) in enumerate(pipeline_steps)
    )
    st.html(f'<div class="rb-pipeline">{pipeline_html}</div>')

    approach_left, approach_right = st.columns(2, gap="large")
    with approach_left:
        with st.container(border=True, height="stretch", key="optimization_card"):
            st.markdown("#### :material/calculate: What is implemented")
            st.markdown(
                """
                - **CP-SAT constraint optimization:** selects compatible 15-minute candidate starts.
                - **Railway rules:** enforce request windows, protected trains, section capacity and crew availability.
                - **Independent validation:** checks the proposed plan after solving.
                - **Explainability:** exposes selected window, crew, disruption, solver status and validation result.
                """
            )
    with approach_right:
        with st.container(border=True, height="stretch", key="ai_boundary_card"):
            st.markdown("#### :material/psychology_alt: AI boundary")
            st.warning(
                "CP-SAT is constraint optimization—not machine learning.",
                icon=":material/priority_high:",
            )
            st.markdown(
                "RailBlock AI is an **AI-assisted intelligent planning system** built from optimization, explicit rules and validation. No trained ML model is implemented or claimed in this prototype."
            )

    with st.container(border=True, key="objective_card"):
        st.markdown("#### :material/target: Objective aligned to asset availability")
        st.code(
            "maximize 100 × priority × maintenance minutes\n"
            "       − 12 × weighted train-overlap minutes\n"
            "       − start lateness",
            language="text",
        )
        st.caption(
            "The objective rewards priority-weighted maintenance completion inside safe windows while penalizing operational interaction and late starts. This supports the PS goal of maximizing asset availability without claiming measured field impact."
        )

with limits:
    render_section_heading(
        "Safety and deployment boundary",
        "Limits & integration",
        "A credible prototype is explicit about what is implemented and what remains future work.",
    )
    limit_columns = st.columns(3, gap="medium")
    with limit_columns[0]:
        with st.container(border=True, height="stretch"):
            st.markdown("#### :material/check_circle: Current prototype")
            st.markdown(
                "Deterministic single-day decision support over simulated CSV data, with CP-SAT optimization and independent validation."
            )
    with limit_columns[1]:
        with st.container(border=True, height="stretch"):
            st.markdown("#### :material/block: Not claimed")
            st.markdown(
                "No live railway connectivity, official operational data, production deployment, safety certification, trained ML model, predictive accuracy or measured field impact."
            )
    with limit_columns[2]:
        with st.container(border=True, height="stretch"):
            st.markdown("#### :material/route: Future integration path")
            st.markdown(
                "Authenticated timetable, asset, crew and possession adapters; configurable division rules; audit logs; role-based approval; rolling-horizon re-planning; shadow-mode validation."
            )

    st.warning(
        "All operational data and KPIs are deterministic simulated/demo data. Human authorization and railway safety procedures remain mandatory.",
        icon=":material/health_and_safety:",
    )
