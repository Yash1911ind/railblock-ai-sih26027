# Optimization formulation

Project: SIH26027 · Crafters· Chandighar University

## Current demo

For maintenance request `i` and feasible candidate start `t`, binary variable `x(i,t)=1` means the block is selected at that time. Candidates are generated every 15 minutes inside both the request window and a section candidate window.

Hard constraints:

1. at most one candidate is selected per request;
2. candidates overlapping a protected train are removed;
3. overlapping candidates cannot share the same section;
4. overlapping candidates cannot share the same crew.

The demo maximizes this integer score:

```text
sum x(i,t) * [100 * priority(i) * duration(i)
              - 12 * weighted_train_overlap(i,t)
              - minutes_after_earliest_start(i,t)]
```

This makes safety/capacity non-negotiable while allowing the objective to trade maintenance value against permitted operational interaction. We report solver status and validate the output independently.

## What is and is not AI

Constraint optimization is the correct intelligent search technique here: it evaluates a combinatorial plan space under explicit rules. We do not attach a classifier merely for an “AI” label. In a future system, ML is useful only for evidence-based estimates such as duration distributions, asset failure risk and train-running uncertainty. Prediction outputs would feed the optimizer with confidence bounds, remain separately evaluated, and never relax a safety rule.

## Scaling path

- rolling planning horizons and section-based decomposition;
- precomputed candidate windows and dominance pruning;
- warm starts from the published plan;
- lexicographic objectives (safety feasibility, urgent work, disruption, utilization, stability);
- robust/scenario optimization for uncertainty;
- fixed solver time with incumbent/optimality-gap reporting;
- human-override reasons retained in the audit trail.

## Phase 1 — risk & explainability layer (advisory)

`railblock/risk.py` adds a deterministic, rule-based asset risk score (0-100) computed
from `condition_score`, `last_maintenance_days`, and any optional columns that happen to
be present (asset age, traffic/load, historical failures). It is a transparent formula,
not a trained ML model, and is not validated against real railway failure data. It never
overwrites the manual `priority` column the optimizer consumes — it only produces an
`ai_suggested_priority` shown alongside the manual value for a controller to review.

`railblock/explain.py` adds a natural-language explanation per request, built only from
the selected block, the candidate options the solver actually considered
(`PlanningResult.options_by_request`), the independent validator's conflicts, and the
asset's risk score. It does not re-run, wrap, or alter the optimizer.

## Phase 2 — coordination, disruption re-planning, what-if simulation

**Currently implemented:**

- `railblock/coordination.py` — multi-department (Engineering / S&T / Traction, where
  "Traction" is this dataset's `Electrical` department) coordination detection. It checks,
  from actual request/window data, whether two or more same-section requests could share
  one common possession: different departments, different crews, overlapping *requested*
  windows, and a candidate window able to host the combined duration (`max` of the
  individual durations). It never assumes compatibility — most same-section pairs in the
  demo data are correctly rejected (window mismatch), and exactly one real opportunity is
  found (SEC-C, `MR-001`+`MR-006`, 60 min estimated reduction). It does not call
  `optimize_blocks()` and does not modify `optimizer.py`.

  *Why advisory-only:* making the CP-SAT model actually schedule a joint block would mean
  relaxing the existing same-section mutual-exclusion constraint selectively for compatible
  groups, generating combined-candidate variables spanning multiple requests, and
  restructuring the per-request reward and crew-assignment logic. That is a significant,
  higher-risk change to the core optimizer and was intentionally deferred rather than made
  as part of this phase.

- `railblock/disruptions.py` — represents disruptions explicitly (`TRAIN_DELAY`,
  `BLOCK_UNAVAILABLE`, `EMERGENCY_MAINTENANCE`, `DURATION_INCREASE`,
  `TEMPORARY_RESTRICTION`) and applies them to fresh copies of `requests`/`trains`/`windows`
  — the caller's originals are never mutated. `TEMPORARY_RESTRICTION` is modeled as a
  synthetic non-delayable "train" occupying the restricted section/time, which reuses the
  optimizer's existing protected-train exclusion logic with zero changes to `optimizer.py`.
  `replan_after_disruption()` orchestrates: current plan → disruption → updated state →
  the *same* `optimize_blocks()` → validation (already built into `optimize_blocks()`) →
  before/after comparison built only from real `PlanningResult` data.

- `railblock/scenarios.py` — `run_what_if_scenario()` is a thin, explicitly ephemeral
  wrapper around `replan_after_disruption()` for the "What-If Simulation" tab: it operates
  on temporary copies, supports multiple simultaneous disruptions, and never writes back to
  the caller's DataFrames, session state, or the live schedule.

**Controller-in-the-loop design:** every Phase 2 output is labeled as an AI
recommendation/suggestion/simulation result requiring controller review — coordination
groups, re-planned schedules and what-if outcomes are never presented as an autonomous
change to railway operations.

**Future integration (not built yet):** joint-block scheduling inside the CP-SAT model
itself; a persisted "possession/block" entity distinct from a candidate window; richer
disruption types (crew unavailability, multi-day restrictions); a *persisted*
controller approve/reject workflow with an audit trail (Phase 3 adds a session-state-only
version — see below).

## Phase 3 — Digital Twin and Control Room UI

**Digital Twin (`railblock/digital_twin.py`):** a visualization and simulation layer
built over data already computed elsewhere in the app — it is not a live representation
of railway infrastructure. It calls neither `optimize_blocks()` nor a second copy of the
risk engine; it only reshapes an existing `PlanningResult`, the existing
`calculate_asset_risk()`, and the CSV-backed `assets`/`trains`/`windows` tables into:

- a per-section status (`AVAILABLE` / `MAINTENANCE` / `CONFLICT` / `RESTRICTED`), derived
  from whether a validator conflict, a scheduled block, or a simulated
  `TEMPORARY_RESTRICTION` touches that section — in that priority order;
- a per-section risk level, the maximum of `calculate_asset_risk()` over that section's
  assets;
- trains and blocks belonging to each section, always labeled `"Scheduled position
  (simulation)"` — never a live or GPS position, since none exists in this dataset;
- a schematic (not geographic) horizontal network figure connecting sections in ID order.

**Control Room (the redesigned first tab):** a single-screen operational summary —
system status strip, 6 KPI cards (Active blocks, Critical assets, Pending maintenance,
Conflicts, Deferred requests, Estimated delay impact — all read directly from the current
`PlanningResult`/risk table, never invented), a compact Digital Twin network view, an AI
Operations Command Center (top-risk asset + recommended block, reusing `risk.py` and
`explain.py` verbatim), a data-driven Alert Center (every alert traces to an actual
conflict, deferral, CRITICAL asset, or open disruption — "no alerts" renders as
`✓ No critical operational alerts` when nothing is true), an Active Blocks panel, and
compact Coordination/Disruption widgets that reuse the Coordination and Re-planning tabs'
existing engines rather than recomputing anything.

**Controller review actions:** Approve / Modify / Reject buttons write only to
`st.session_state.controller_decisions` for this browser session — no external system is
contacted, and every such control is captioned `"Prototype action — no external railway
system is controlled."`

**Analytics tab:** the original before/after comparison and conflict chart (unchanged,
relocated here from the old "Command overview" tab) plus risk distribution, maintenance
priority distribution, block utilization, and per-request train impact — all charted only
from data the app already computes.

**Weekly Planner tab:** the demo dataset covers exactly one simulated day, so only "Day 1"
shows a real CP-SAT-computed schedule; days 2–7 are explicit placeholders
("Not yet scheduled — this demo dataset contains only one simulated day"), not fabricated
data. Multi-day rolling-horizon planning stays documented future work, consistent with the
Scaling path section above.

**Demo Mode:** an optional sidebar toggle that renders an 11-step guided-tour checklist at
the top of the Control Room tab. Every line reads a real, already-computed value (asset
ID, risk score, coordination count, solver status, conflict counts) — nothing is scripted
or faked.

**Performance:** the Control Room, Digital Twin, Coordination widget, and Analytics tabs
all reuse one `risk_table`, one `opportunities` list, and one `section_states` list
computed exactly once per script rerun (immediately after the single `optimize_blocks()`
call already made for the main plan) — no tab triggers an additional CP-SAT solve just to
render a card.

## Phase 4 — approved priority, joint-block investigation, KPI engine, demo/audit

**Approved AI priority (`railblock/approval.py`):** the optimizer's manual `priority`
column is still never overwritten automatically. `build_priority_review_table()` shows
manual vs. AI-suggested priority side by side; `apply_approved_priorities()` is a pure
function that returns a *new* requests table with the override applied only for
request_ids a controller explicitly approved in the UI. `optimize_blocks()` is never
called with this automatically — the "AI Asset Health" tab requires an explicit
"Apply approved priorities and re-optimize" click, and the result is shown as a separate
comparison, never silently swapped into the live plan.

**Joint-block coordination — investigated, not forced in:** Phase 4 inspected
`optimizer.py`'s same-section mutual-exclusion constraint to see whether an approved
coordination group could safely become a real CP-SAT joint block. Two paths were found:

1. Relax the mutual-exclusion constraint for an approved pair's candidates. This is a
   small change to `optimizer.py`, but the *independent* validator (`validation.py`)
   would then flag every such coordinated block as a "Resource" conflict (overlapping
   section use) — unless `validation.py` also became aware of approved coordination,
   which would compromise the validator's independence from upstream decisions, a
   property this project has treated as non-negotiable since Phase 0.
2. Merge a group into one multi-crew synthetic request. This requires `crew_id` to
   become a set everywhere it's used in candidate generation, pairwise exclusion, and
   the validator's crew-conflict check — a genuine schema change, not a small additive
   one.

Both paths were judged out of scope for a safe same-phase change. Per the explicit
fallback in the Phase 4 brief, `coordination.py` instead gained
`build_optimization_proposal()`: once a controller approves a coordination group, this
produces a concrete, inspectable preview (participating crews, shared time window,
combined duration) explicitly labeled `"PROPOSAL ONLY — not yet applied to the CP-SAT
optimizer"`. Real joint-block CP-SAT scheduling remains documented future work requiring
a coordinated redesign of `optimizer.py` **and** `validation.py` together.

**Centralized KPI engine (`railblock/metrics.py`):** twelve metrics computed once from
real `PlanningResult`/risk/coordination data (scheduled/deferred counts, conflicts,
maintenance duration, train impact, average delay impact, high/critical-risk assets
addressed, coordination opportunities, estimated possession reduction, schedule
utilization, and a risk-weighted maintenance coverage estimate). `compare_metrics()`
diffs any two such dicts — used for Baseline vs Optimized, Baseline vs Disruption Re-plan,
and the SIH Demo Mode "Before vs After" step, so the same number is never computed two
different ways in two different tabs.

**Demo scenario engine (`railblock/demo.py`):** six deterministic scenarios
(`normal_planning`, `high_risk_asset`, `train_delay`, `block_unavailable`,
`emergency_maintenance`, `multi_department_coordination`), each a thin orchestration over
the existing risk/coordination/disruption/optimizer functions — no scenario computes a
result independently or hardcodes an outcome.

**Audit trail (`railblock/audit.py`):** a session-scoped, in-memory event log
(timestamp, action, entity, reason) recorded at every approval, re-plan, simulation and
disruption action in the UI. This is a prototype demonstration mechanism, not a
regulatory-compliance record, and is explicitly labeled as such.

**System Status (`railblock/system_status.py`) and Data Quality
(`railblock.data.data_quality_report`):** a runtime self-check that each bundled engine
(CP-SAT, validator, risk, coordination, re-planning, simulation, digital twin) imports and
initializes correctly, and a read-only summary of what is actually loaded (record counts,
missing values, which optional risk columns are present). Neither claims or checks any
external system connectivity — none exists in this prototype.

## Known simplifications

The demo has no detailed network topology, headway propagation, bidirectional line logic, isolation zones, equipment movement, possessions spanning midnight, probabilistic duration, precedence, or formal rule catalogue. These are future configuration/modeling tasks, not hidden claims.
