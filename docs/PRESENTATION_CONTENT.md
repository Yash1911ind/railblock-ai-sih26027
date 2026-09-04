# SIH presentation-ready content

This is slide copy and visual direction, not the final deck. Apply it to the official SIH template when supplied; do not change mandatory headings.

## Slide 1 — RailBlock AI

**AI-powered automatic block planning for safer maintenance access and resilient train operations**  
SIH26027 · Crafters· Chandighar University

Visual: clean rail corridor with a maintenance possession window highlighted.

## Slide 2 — The planning collision

- Maintenance needs uninterrupted access.
- Trains need scarce section capacity.
- Departments and crews share the same windows.
- A locally good decision can create a network conflict.

Visual: three inputs converging on one constrained timeline. Cite public railway block-working references in notes.

## Slide 3 — One decision-support loop

**Ingest → validate → generate candidates → optimize → verify → recommend → re-plan**

Callouts: hard safety rules; explainable score; human approval.

## Slide 4 — What the engine sees

Inputs: train occupations, maintenance duration/priority/window, section capacity, crews/equipment, operating rules.  
Outputs: block start/end, resources, affected paths, deferrals, reasons, KPIs and alternatives.

## Slide 5 — Optimization that judges can audit

Hard: protected trains, permitted windows, section capacity, crew capacity.  
Objective: maximize priority × completed maintenance; minimize permitted disruption and lateness.  
Method: CP-SAT discrete scheduling. ML is reserved for evidence-backed duration/risk prediction.

## Slide 6 — Working prototype

Use current UI screenshots: command overview, recommended timeline and independent conflict validator. Add a clear “SIMULATED DEMO DATA” label.

## Slide 7 — Before vs after

Baseline: naive earliest-start placement; conflicts detected after planning.  
Optimized: conflict-free recommendation under the demo rules; deferred work remains explicit.  
Show only metrics reproduced by the running app and label them simulated.

## Slide 8 — Re-planning under change

Event arrives → freeze/retain commitments → regenerate candidates → optimize → show differences → planner approves.  
Demo action: cancel one simulated train path and re-plan.

## Slide 9 — Production-shaped architecture

Adapters → canonical snapshot → rules → optional predictions → optimizer → independent validator → approval workflow → dashboard/API.  
Side rail: provenance, RBAC, audit log, monitoring.

## Slide 10 — Feasibility roadmap

1. Rule/data discovery and representative snapshot.
2. Historical replay and shadow planning.
3. Bounded divisional pilot with acceptance criteria.
4. Controlled integration and monitored rollout.

No partnership or deployment claim.

## Slide 11 — Impact framework

Measure: feasible-plan rate, protected conflicts, maintenance completion, planner overrides, plan stability, computation time and realized operational effect.  
Separate simulated prototype KPIs from future pilot KPIs.

## Slide 12 — Why RailBlock AI

**Feasible by construction · integrated across departments · explainable · disruption-ready · honest about evidence**

Close: “Give every maintenance minute a safe, accountable place in the timetable.”

## Official team information

Crafters· Chandighar University  
Yash Nalandwar · Manpreet Kaur · Niraj Patil · Adarsh Kumar · Vishal Kumar · Arzoo

No roles, registration numbers, emails or phone numbers are inferred.
