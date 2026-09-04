# Data, assumptions and limitations

Project: SIH26027 · Crafters· Chandighar University

## Classification

- **Public information:** general block-working concepts cited in the README; OR-Tools capabilities documented by Google.
- **Simulated/demo:** all CSV rows, section names, train names/times, condition scores, maintenance durations/priorities, solver outputs and KPIs.
- **Assumptions:** 12-hour horizon; 15-minute start grid; one possession capacity per section; protected trains cannot overlap; delay-tolerant train interaction is penalized; each request needs one named crew.
- **Future integration:** authoritative timetables, asset/work systems, rosters, disruption feeds, identity/approval and publishing interfaces—subject to discovery and railway authorization.

## Synthetic data design

The scenario is deterministic and small enough to explain. It deliberately includes protected train conflicts, shared crews and competing windows so the baseline fails and the optimizer must make real trade-offs. IDs and names are fictional.

For a larger synthetic benchmark, generate sections, time-window occupations, correlated maintenance demand, resource calendars and disruption scenarios from documented distributions. Publish the random seed, generator version and validation rules. Do not tune only on the demonstration case.

## KPI definitions

- **Maintenance coverage:** scheduled maintenance minutes / requested maintenance minutes.
- **Protected conflicts:** validator count of scheduled blocks overlapping non-delayable simulated train paths.
- **Weighted disruption minutes:** permitted overlap minutes × simulated train importance. This is a proxy, not passenger delay.
- **Block utilization:** selected maintenance minutes / total candidate-window minutes. Overlapping section windows are simply summed in this demo.
- **Planning time:** local wall-clock solver and result-construction time; not a production benchmark.

## Phase 1 risk & explainability layer

Phase 1 uses a transparent rule-based asset risk engine over synthetic demonstration
data. It is an advisory component and does not represent a field-validated railway ML
model. It does not claim real Indian Railways sensor integration, real
failure-prediction accuracy, production deployment, field validation, or access to
proprietary railway systems. The AI-suggested priority it produces is shown next to the
manual request priority for human review and never silently overwrites it.

## Evaluation before deployment

Replay historical snapshots in shadow mode; compare feasibility, planner overrides, computation time, schedule stability and realized operational impact. Safety-rule conformance must be independently verified. Any duration/risk model requires train/test separation, calibration, subgroup checks, drift monitoring and a documented fallback.
