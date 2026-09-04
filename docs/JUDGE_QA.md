# Judge questions and defensible answers

Prepared for Crafters, Chandighar University — SIH26027.

**Is this actually AI?**  
It is constraint-based AI/operations research: CP-SAT searches a combinatorial schedule under logical and integer constraints. We reserve ML for future predictions where historical data can support measured accuracy.

**Why not a greedy algorithm?**  
Greedy choices can consume a section or crew needed by a more valuable request. CP-SAT considers compatible combinations and reports feasible/optimal status within a time limit.

**Where did the data come from?**  
Every operational row and KPI in the demo is synthetic and labeled. Public railway manuals inform only the problem framing. Production work begins with authoritative schema and rule discovery.

**Are you claiming fewer delays?**  
No field impact is claimed. “Weighted disruption minutes” is a simulated planning proxy. Historical replay and a controlled shadow pilot would establish whether operational KPIs improve.

**How is safety guaranteed?**  
This prototype cannot guarantee operational safety. It encodes illustrative hard constraints and independently validates its output. Production rules require railway-owner verification, safety assurance, formal authorization and a fail-safe human workflow.

**What happens if no feasible plan exists?**  
Requests are deferred rather than violating hard constraints. A production version would return an infeasibility explanation and ranked relaxations that require authorized approval.

**How do you handle disruption?**  
The demo rebuilds the plan after a train-path change. Production would use rolling-horizon optimization, freeze near-term commitments, penalize schedule churn and preserve an audit trail.

**How will this scale?**  
Use section/time decomposition, candidate pruning, warm starts, bounded solve time and incumbent reporting. Scale must be demonstrated on representative historical snapshots; it is not claimed from this small demo.

**How is this better than manual planning?**  
It rapidly checks combinations, makes trade-offs explicit, catches conflicts consistently and preserves reasons. It supports planners; it does not discard their local knowledge or authorization role.

**What about integration with Indian Railways?**  
We have not claimed an API or partnership. We propose adapter contracts after confirming authoritative systems, ownership, latency, identity, cyber controls and publishing processes with the relevant railway stakeholders.

**What is innovative?**  
The defensible innovation is the combination of integrated multi-department planning, explicit hard-rule optimization, independent validation, explainable recommendations and low-churn event re-planning—not an opaque prediction dashboard.

## Risks judges may probe

- incomplete or inconsistent rules and topology;
- poor duration estimates and disruption uncertainty;
- optimizer scale and response time;
- user trust, overrides and accountability;
- integration/cybersecurity and data ownership;
- metric gaming or mistaking a proxy for realized delay.

Mitigate through rule ownership, data-quality gates, confidence bounds, shadow replay, auditability, bounded pilots and pre-agreed acceptance criteria.
