# Demo script and pitches

**Team:** Crafters, Chandighar University  
**Members:** Yash Nalandwar, Manpreet Kaur, Niraj Patil, Adarsh Kumar, Vishal Kumar, Arzoo

## End-to-end scenario

The simulated division has three sections, nine train paths, six assets and six maintenance requests. The naive baseline places every job at its earliest allowed time, creating protected-train and shared-resource conflicts. RailBlock AI searches safe candidate starts, prioritizes high-value maintenance, limits permitted train interaction and independently validates the result. Cancelling a demo train triggers a fresh plan, illustrating rolling re-planning.

All on-screen values are simulated.

## 30-second pitch

Railway maintenance needs track time, but every block competes with train operations and scarce crews. RailBlock AI converts work requests, train paths, windows and resources into a validated block recommendation. Its CP-SAT engine treats safety and capacity as hard constraints, then maximizes priority-weighted maintenance while minimizing operational interaction. Our working prototype shows the conflicting baseline, an explainable optimized plan and rapid re-planning—using clearly labeled simulated data and keeping authorization with railway staff.

## One-minute pitch

Today, block planning requires multiple departments to coordinate scarce possession time around a dense timetable. The challenge is combinatorial: a locally convenient job can block a protected train, consume a shared crew, or prevent more urgent work elsewhere. RailBlock AI creates a single decision-support layer. It validates inputs, generates candidate windows, removes unsafe options, and uses constraint programming to select a compatible plan. The objective rewards maintenance priority and duration and penalizes permitted train interaction and lateness. Every recommendation shows its time, section, crew, disruption score and validation result. In our simulated demo, a naive earliest-start plan creates conflicts; the optimized plan removes protected conflicts and can be regenerated when conditions change. The next step is shadow-mode integration with authoritative data and rule validation—not an unearned production claim.

## Three-minute explanation

1. **Problem:** maintenance blocks are necessary for safe asset upkeep, but they temporarily constrain railway capacity. Engineering, S&T and Electrical requests compete with train paths and resources.
2. **Inputs:** section windows, train occupations, maintenance duration/priority/deadline, asset, department and crew.
3. **Engine:** candidate starts are generated at 15-minute intervals. Protected-train overlap, request-window violations, section double-booking and crew double-booking are hard constraints. CP-SAT chooses the best compatible set using a transparent score.
4. **Trust:** the UI labels data as simulated, exposes the objective and separately validates the output. A planner remains the approver.
5. **Demo:** compare the intentionally naive baseline with the colored optimized timeline; inspect conflicts; cancel a train and re-plan.
6. **Roadmap:** confirm rules and schemas, replay historical plans in shadow mode, integrate adapters and approval workflow, then pilot within a bounded planning area with measurable acceptance criteria.
