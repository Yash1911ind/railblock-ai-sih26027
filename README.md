# 🚆 RailBlock AI

### AI-Powered Automatic Block Planning for Indian Railways

> **Smart India Hackathon 2026 · SIH26027**  
> **Team Crafters· Chandighar University**

RailBlock AI is an **explainable AI-assisted decision-support prototype** for planning railway maintenance blocks while minimizing disruption to train operations.

It evaluates **maintenance requests, train paths, time windows, sections, crews, priorities and operational conflicts** to recommend a feasible and optimized block plan.

---

## 🎯 SIH Problem Statement

**SIH26027 — AI-Powered Automatic Block Planning to Maximize Asset Availability for Train Operations on Indian Railways**

### Our Objective

> **Maximize asset availability while minimizing operational disruption and respecting railway planning constraints.**

---

## 💡 Our Solution

```text
Maintenance Requests + Train Schedule + Constraints
                         ↓
                  RailBlock AI Engine
                         ↓
                Constraint Validation
                         ↓
                 CP-SAT Optimization
                         ↓
              Recommended Block Plan
                         ↓
          Timeline + KPIs + Explanation
```

### ✨ Key Features

- 🛠️ Maintenance requests with duration, priority, department, section, crew and window
- 🚆 Train-path awareness with protected and delay-tolerant paths
- 🧠 **Google OR-Tools CP-SAT** constraint optimization — the single scheduling engine
  behind every tab in the app
- ⏱️ 15-minute candidate block start resolution
- 🚫 Hard constraints for train, section, window and crew conflicts
- 🎯 Priority-aware objective with operational-interaction penalties
- 🔍 Independent post-solve conflict validation, never modified to accommodate an AI or
  coordination decision
- 📊 Before/after planning KPIs and a 12-metric centralized KPI engine
- 📅 Visual possession / block timeline and a weekly planner view
- 🔄 Scenario-based dynamic re-planning and what-if simulation (temporary copies only —
  the live plan is never altered by a simulation)
- 💬 Explainable recommendations generated from the solver's actual candidate options
- 🧠 Transparent, rule-based **AI asset risk scoring** — advisory only, never silently
  applied to the optimizer
- 🔗 Multi-department coordination detection (Engineering / S&T / Traction) with a
  controller-approved "Optimization Proposal" preview
- 🗺️ Digital Twin — a schematic section/train/block visualization, not a live railway map
- ✅ Controller-in-the-loop approval workflow with a session-scoped audit trail
- 🏆 A guided **SIH Demo Mode** walkthrough with one-click reset

---

## 🏗️ Solution Architecture

```text
Data (assets, requests, trains, windows, crews)
                 ↓
         AI Asset Risk (advisory)
                 ↓
      Maintenance Priority (manual + AI-suggested)
                 ↓
   Multi-Department Coordination (advisory)
                 ↓
      CP-SAT Optimization (Google OR-Tools)
                 ↓
        Independent Conflict Validation
                 ↓
      Explainable Recommendation
                 ↓
            Controller Review
                 ↓
             Approved Plan
                 ↓
   Disruption / What-If Simulation
                 ↓
          Dynamic Re-planning
                 ↓
    Digital Twin  ·  Analytics  ·  Audit Trail
```

The AI layer *predicts and prioritizes*; the CP-SAT solver is the only component that
*optimizes*; the independent validator *checks feasibility* without ever being modified
to accommodate an AI or coordination decision; the controller *approves* — see
`docs/ARCHITECTURE.md` for the full reasoning.

---

## 🧮 Why Optimization Instead of Greedy Scheduling?

A greedy approach may simply choose the **earliest available slot**. Railway block planning, however, involves multiple interacting constraints.

RailBlock AI considers the planning problem globally across:

- maintenance priority;
- train movement conflicts;
- maintenance duration;
- section availability;
- crew availability;
- permitted maintenance windows;
- operational interaction penalties.

Therefore, the system searches for a **better overall feasible plan**, rather than making an isolated earliest-slot decision.

---

## ⚙️ Technology Stack

| Layer | Technology |
|---|---|
| Application | **Streamlit / AI Studio prototype** |
| Optimization | **Google OR-Tools CP-SAT** |
| Language | **Python** |
| Data | **Simulated railway scenarios** |
| Validation | **Constraint checks** |
| Testing | **Pytest** |
| Version Control | **GitHub** |

---

## 🌐 Live Prototype

### 🚀 [Open RailBlock AI Prototype](https://railopt-ai-sih26027.ai.studio/)

**RailOpt AI — SIH26027 Prototype**

This is the primary interactive prototype for the SIH solution, demonstrating the proposed railway block-planning workflow, optimization logic, scheduling decisions and explainable outputs.

> **Prototype note:** The demonstration uses simulated data and is intended for SIH evaluation and concept demonstration. It does not represent official Indian Railways operational data.

---

## 🎥 SIH Demo Video

### ▶️ [Watch the RailBlock AI Demo Video](https://drive.google.com/drive/folders/1v0bAu8lX4_bdRO7anGyXyl2l35bPJfX5)

The demo video presents the working prototype and demonstrates the **SIH26027 solution workflow, block-planning process, optimization and key system outputs**.

> **Demo:** Smart India Hackathon 2026 · SIH26027 · Crafters

---

## 👥 Team — Crafters

**Institution:** Chandighar University  
**Problem Statement:** SIH26027

| Team Member |
|---|
| Yash Nalandwar|
| Manpreet Kaur |
| Niraj Patil |
| Adarsh Kumar |
| Vishal Kumar |
| Arzoo |

---

## 📁 Project Structure

```text
railblock-ai-sih26027/
│
├── app.py                    # Streamlit application (single entry point)
├── railblock/
│   ├── optimizer.py          # CP-SAT optimization engine (core scheduler)
│   ├── validation.py         # Independent conflict validation
│   ├── data.py                # Data loading + data quality report
│   ├── risk.py                # AI asset risk / priority engine (advisory)
│   ├── explain.py             # Explainable recommendations
│   ├── coordination.py        # Multi-department coordination detection
│   ├── disruptions.py         # Disruption representation + re-planning
│   ├── scenarios.py           # What-if simulation (ephemeral)
│   ├── digital_twin.py        # Section/train/block visualization data
│   ├── approval.py            # Controller-approved AI priority workflow
│   ├── metrics.py             # Centralized KPI engine
│   ├── demo.py                 # Deterministic demo scenarios
│   ├── audit.py                # Session-scoped audit trail
│   └── system_status.py        # Engine readiness self-check
│
├── data/                     # Simulated demonstration data
├── tests/                    # One test module per railblock/ file
├── docs/                     # Architecture, algorithm & SIH material
├── requirements.txt          # Runtime dependencies
├── pyproject.toml            # Project configuration
└── README.md                 # Project documentation
```

---

## ▶️ Run Locally

```bash
git clone https://github.com/rohitbandi0311-afk/railblock-ai-sih26027.git
cd railblock-ai-sih26027
pip install -r requirements.txt
streamlit run app.py
```

Run tests:

```bash
pytest
```

---

## 🔬 Research & References

The project is informed by:

- Indian Railways material on line and integrated blocks
- Indian Railways Track Machine Manual and maintenance planning concepts
- Google OR-Tools CP-SAT constraint programming documentation
- Railway asset, maintenance and operational scheduling concepts

Detailed assumptions, formulation, integration considerations and SIH judge-preparation material are available in `docs/`.

---

## ⚠️ Prototype Disclaimer

This repository is an **SIH proof-of-concept prototype**.

- All train, asset, maintenance, time and result data are **simulated demonstration data**.
- The system does **not** represent official Indian Railways operational data.
- It does **not replace railway authorization, operating rules, safety procedures or human decision-making**.
- Real-world TMS/SMMS/TDMS integration would require appropriate authorization, interfaces, security controls and domain validation.

---

## 🚀 Vision

RailBlock AI aims to evolve into an **intelligent railway maintenance planning assistant** that combines operational information with maintenance requirements and continuously recommends safer, more efficient block plans.

> **Plan smarter. Maintain faster. Keep trains moving. 🚆🇮🇳**

---

<div align="center">

### 🇮🇳 SMART INDIA HACKATHON 2026

**SIH26027 · RailBlock AI · Crafters**

</div>
