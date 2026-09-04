# SIH Demo Guide

Project: SIH26027 · Crafters· Chandighar University

This is the presenter's script for the **🏆 SIH Demo Mode** tab in the running app
(`streamlit run app.py`). Every step reads real values from the synthetic demo dataset
and calls the same functions used throughout the rest of the app — nothing on this tab
is scripted or faked.

Before presenting: open **🏆 SIH Demo Mode** and click **🔄 RESET DEMO** once, so the
walkthrough starts from the base scenario.

## The 11-step story

| Step | What it shows | Where the number comes from |
|---|---|---|
| 1. Asset Health | The highest-risk asset system-wide (ID, level, 0–100 score) | `railblock/risk.py` over `data/assets.csv` |
| 2. Maintenance Request | The pending request tied to that asset | `data/maintenance_requests.csv` |
| 3. AI Recommendation | Manual priority vs. AI-suggested priority | `railblock/risk.py::suggest_priority` |
| 4. Coordination Opportunity | A same-section, cross-department group that could share one possession | `railblock/coordination.py` |
| 5. Generate Optimized Block | The live CP-SAT solver status and scheduled/deferred counts | `railblock/optimizer.py::optimize_blocks` |
| 6. Explain Recommendation | A natural-language reason for the selected/deferred schedule | `railblock/explain.py` |
| 7. Controller Approval | Approve / Modify / Reject buttons (session-state only) | `render_controller_actions` in `app.py` |
| 8. Introduce Disruption | Simulated: Train TR-101 delayed +20 minutes, re-planned | `railblock/disruptions.py::replan_after_disruption` |
| 9. Run What-If Simulation | Simulated: candidate window W-A1 unavailable, on a temporary copy | `railblock/scenarios.py::run_what_if_scenario` |
| 10. Dynamic Re-planning | Conflicts / deferred / train-impact delta from step 8 | Same `ReplanResult.comparison` shown in 🚨 Re-planning |
| 11. Before vs After | All 12 KPIs, baseline vs. current optimized plan | `railblock/metrics.py::compare_metrics` |

Steps 3, 4 and 7 link to the tabs where the actual approve/reject actions live (🧠 AI
Asset Health, 🔗 Coordination) — clicking there also appends to the session's Audit
Trail, visible at the bottom of the Demo Mode tab.

## Suggested narration

1. **Open with Control Room.** "This is a railway operations decision-support prototype
   — everything you'll see is computed live from a synthetic demo dataset, never faked."
2. **Point at the KPI cards and Alert Center.** "Every number here — active blocks,
   critical assets, conflicts — is read directly from the CP-SAT solver's actual output
   or the risk engine, never invented for the demo."
3. **Switch to 🏆 SIH Demo Mode and walk steps 1–7.** Emphasize step 3: "The AI never
   changes the schedule by itself — a controller has to approve it first, and even then
   only after an explicit re-optimize click."
4. **Steps 8–10: click Introduce Disruption, then Run What-If.** "Same CP-SAT solver,
   same validator, applied to a hypothetical. The original plan is never touched — watch
   the Block Optimizer tab, it hasn't changed."
5. **Step 11 and 📊 Analytics.** "Baseline is a naive earliest-start scheduler; Optimized
   is the same CP-SAT engine used everywhere else. The conflict count dropping to zero
   is the independent validator's own conclusion, not the optimizer grading its own work."
6. **Close on 📐 Architecture or 📋 SIH Evidence** if judges want the technical summary in
   one screen.

## If something goes wrong live

- **Reset Demo** (top of the SIH Demo Mode tab) restores session state to the base
  scenario without restarting the app or touching any CSV file.
- The sidebar's **Reset base scenario** button does the same for just the train-
  cancellation scenario, if that's all that needs undoing.
- Nothing in this app writes to `data/*.csv` — a full process restart (`streamlit run
  app.py`) always comes back to the exact same synthetic dataset.

## What this demo does not claim

Per `docs/DATA_AND_LIMITATIONS.md` and the disclaimers repeated throughout the app: no
live railway connectivity, no real Indian Railways operational data, no trained ML model,
no autonomous control of any railway system, and no measured real-world impact. Every
number is either directly computed from the synthetic CSVs, or explicitly labeled
"Estimated" / "Simulation" / "Prototype demonstration."
