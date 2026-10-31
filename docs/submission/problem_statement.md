# OnboardIQ: Multi-Agent KYC/AML Onboarding System
## Updated Problem Statement & Research Scope

**Course:** CSE3101 Agentic AI  
**Repository:** `OnBoardIQ`  
**Milestone:** Midterm Project Update / Submission  

---

### 1. Problem Context & Motivation

Know-Your-Customer (KYC) and Anti-Money Laundering (AML) onboarding are legally mandatory prerequisites across global banking and financial services. Current institutional onboarding workflows remain slow, fragmented, and vulnerable:

1. **High Latency & Analyst Fatigue:** Document extraction, identity verification, registry lookups, sanctions screening, and beneficial ownership resolution are predominantly executed sequentially by human analysts. Manual re-keying and searches lead to multi-day turnaround times and high customer abandonment rates.
2. **False Positives in Screening:** Common namesake matches against public sanctions and Politically Exposed Persons (PEP) lists generate false-positive alarms that consume analyst capacity without reducing regulatory exposure.
3. **Weak Audit Provenance:** Risk assessments and compliance rationales often fail to provide unbroken links between specific document evidence, screening scores, and final onboarding decisions, creating compliance audit vulnerabilities.
4. **Data Privacy Exposure:** Raw Personally Identifiable Information (PII) spreads across downstream tools and intermediary services, increasing data leak risks.
5. **Adversarial Applicant Manipulation:** Applicants may submit tampered documents, exhibit abusive behavior, claim executive authority to bypass controls, or embed prompt injection instructions within unstructured form fields or uploaded documents to influence automated systems.

---

### 2. Project Objectives

OnboardIQ implements an autonomous, multi-agent onboarding system combining **Google ADK** (hierarchical orchestration and gateway controls) and **CrewAI** (collaborative screening and verification):

- **Objective 1 (Turnaround & Latency):** Automate the lifecycle from raw intake to draft decision, evaluating parallel multi-agent execution against traditional sequential pipelines.
- **Objective 2 (Auditability & Grounded Evidence):** Guarantee 100% decision provenance by logging all intermediate outputs to a zoned, versioned, append-only Blackboard where every risk factor and decision cites resolvable `evidence_ids`.
- **Objective 3 (Privacy by Default):** Isolate sensitive identifying data into a restricted `pii_vault` zone at intake via a Security Gateway, exposing only a sanitized `MaskedProfile` to non-privileged screening agents.
- **Objective 4 (Security & Human-in-the-Loop):** Mitigate prompt injection, toxicity, and social engineering attacks via multi-stage guardrails, and enforce strict decision safeguards: **automated rejections are prohibited**, mandating human compliance review for high-risk and flagged cases.
- **Objective 5 (Open Tool & Protocol Standards):** Expose all capabilities via an isolated FastMCP tool server and decouple agent teams through the Agent-to-Agent (A2A) protocol with discoverable Agent Cards.

---

### 3. What Changed Since the Initial Submission

Since the initial project charter and requirements formulation:

- **Formal Shared State Architecture:** Upgraded from informal inter-agent messaging to an explicit, typed FastAPI/SQLite Blackboard service featuring zoned role-based access control, optimistic concurrency control (HTTP 409 retry), and an immutable event history.
- **A2A & MCP Protocol Decoupling:** Replaced direct Python function imports between agent frameworks with standard A2A protocol contracts (`/.well-known/agent.json`) and FastMCP tool interfaces (`registry_lookup`, `sanctions_screen`, `doc_ocr`, `risk_predict`, `ubo_graph`).
- **Hybrid P2P Messaging Strategy:** Formulated an abstract `MessagingStrategy` interface supporting both pure Blackboard synchronization and direct peer-to-peer data handoffs with background blackboard logging.
- **Corporate Ultimate Beneficial Ownership (UBO) Path:** Introduced NetworkX directed graph analysis to trace corporate ownership networks, detect opaque offshore structures, and screen beneficial owners holding 10% or greater equity.
- **Empirical Evaluation Harness:** Developed an automated evaluation runner (`eval/runner.py`), metrics engine (`eval/metrics.py`), and visualization generator (`eval/plots.py`) running reproducible multi-case sweeps across systematic configurations.

---

### 4. Scope and Boundaries

- **In Scope:**
  - Individual and corporate onboarding workflows.
  - Document OCR field extraction and synthetic tamper scoring.
  - Mock government registry cross-verification.
  - Fuzzy sanctions screening (RapidFuzz against public OFAC, UN, and PEP lists).
  - Corporate UBO path resolution using NetworkX directed acyclic graphs.
  - Machine-learning risk scoring (Scikit-Learn Gradient Boosting) blended with deterministic rules.
  - Multi-stage guardrails (input toxicity, prompt injection, PII leakage, decision validation).
  - Telemetry callback instrumentation (latency, tokens, estimated cost).
- **Out of Scope:**
  - Direct integration with real production government identity databases.
  - Processing of real-world personal data (100% synthetic dataset with seeded generation).
  - Post-onboarding ongoing transaction monitoring and payment rails.
  - Legal certification under banking compliance jurisdictions.

---

### 5. Research Question

> **"How do shared-state blackboard synchronization and hybrid peer-to-peer message handoffs compare across sequential and parallel execution patterns in a multi-agent financial compliance architecture, specifically regarding decision consistency, end-to-end latency, and token consumption?"**

This question is empirically investigated through controlled benchmark sweeps across individual and corporate applicant cases, contrasting runtime distributions and trace metrics between Blackboard vs. Hybrid P2P modes and Sequential vs. Parallel patterns.

