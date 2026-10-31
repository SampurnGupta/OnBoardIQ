# OnboardIQ: Presentation Slide Deck Outline

**Course:** CSE3101 Agentic AI  
**Project:** Multi-Agent KYC/AML Client Onboarding System  
**Frameworks:** Google ADK + CrewAI | **Protocol:** A2A | **State:** Zoned Blackboard

---

## Slide 1: Title & Team
- **Title:** OnboardIQ: Multi-Agent KYC/AML Client Onboarding
- **Subtitle:** An Interoperable, Secure Multi-Agent System with Zoned Blackboard Architecture
- **Key Message:** Combines Google ADK, CrewAI, FastMCP, and A2A to automate high-stakes compliance onboarding with zero false positives and verifiable provenance.
- **Visual:** System Logo, Team Members & Assigned Phase Roles.

---

## Slide 2: The Compliance Dilemma
- **Key Message:** Traditional banking onboarding is manual, siloed, and vulnerable to emerging adversarial prompt injection attacks.
- **Pain Points:**
  - 14–21 days average corporate onboarding cycle time.
  - Multi-tier offshore shell companies conceal true beneficial owners.
  - LLM agents without architectural security leak PII and succumb to jailbreaks.
- **Research Question:** Can an interoperable multi-agent system deliver sub-second onboarding decisions while guaranteeing audit provenance and strict PII isolation?

---

## Slide 3: System Architecture & Framework Interoperability
- **Key Message:** Two industry-leading frameworks coordinated via open standards—Google ADK for governance, CrewAI for role-based screening.
- **Architectural Highlights:**
  - **Google ADK:** Security Gateway, Document Extractor, Risk Scorer, Compliance Reviewer, Client Communicator.
  - **CrewAI:** Identity Verifier, Sanctions Screener, Adverse Media Analyst, UBO Graph Analyst.
  - **A2A Protocol:** Remote procedure calls via standard `/.well-known/agent.json` discovery.
  - **Zoned Blackboard:** Centralized SQLite / Firestore store with optimistic concurrency (`expected_version`).

---

## Slide 4: Zoned Blackboard & Security by Default
- **Key Message:** Zero private state; zero raw PII leaks.
- **Zones & Permissions:**
  - `pii_vault`: Restricted zone. Raw names/addresses never read by screening agents (HTTP 403 enforcement).
  - `intake`, `verification`, `screening`, `risk`, `review`, `system`: Strict role-based read/write access.
  - **Perimeter Guardrails:** Token-level PII guard, toxicity/threat scanner, and injection blocker.
  - **Golden Policy:** Automated rejection is forbidden; high risk mandates human officer escalation.

---

## Slide 5: Standardized External Tools via FastMCP
- **Key Message:** All external capabilities decoupled via the FastMCP protocol on port 8002.
- **The 7 FastMCP Tools:**
  1. `doc_ocr`: Optical Character Recognition with Error-Level Analysis (ELA) tamper scoring.
  2. `registry_lookup`: SQLite government registry verification.
  3. `sanctions_screening`: Fuzzy Jaro-Winkler matching against OFAC SDN & UN Consolidated lists.
  4. `news_search`: Local news corpus investigation with paraphrased summarization.
  5. `ownership_graph`: NetworkX depth-first unravelling of offshore corporate UBOs (> 25%).
  6. `risk_model`: Scikit-learn Gradient Boosting Classifier predicting risk probability.
  7. `policy_rag`: Institutional rule engine auditing drafts against 15 compliance policies.

---

## Slide 6: Agentic Design Patterns: Concurrency & Reflection
- **Key Message:** Orchestration flexes dynamically between Sequential, Parallel, and Reflective loops.
- **Patterns Demonstrated:**
  - **Sequential Pipeline:** Deterministic step-by-step audit trail.
  - **Parallel Concurrency:** ThreadPool concurrent dispatch of screening agents with optimistic concurrency retries.
  - **Reflection Loop:** Compliance Reviewer audits draft against policy rules; triggers automated revision loop with Risk Scorer (capped at 2 cycles).
  - **Client RFI Loop:** Automated clarification requests for low-confidence documents with neutral de-escalation.

---

## Slide 7: Adversarial Testing & Applicant Personas
- **Key Message:** The system maintains risk invariance regardless of applicant temperament or adversarial payloads.
- **Tested Personas (4 Variants Each):**
  - `Cooperative`: Polite, detail-oriented applicant.
  - `Impatient`: Exerts urgency and SLA financial penalty pressure.
  - `Abusive`: Toxic insults and legal retaliation threats (de-escalated without policy disclosure).
  - `Forger`: Deceptive excuses for spliced credentials (caught via ELA tamper score).
  - `Injecting`: Delimiter escapes (`--- SYSTEM OVERRIDE ---`) and jailbreaks (100% blocked at perimeter).

---

## Slide 8: Empirical Evaluation: 48-Run Benchmark Sweep
- **Key Message:** Rigorous empirical proof across a 24-case benchmark dataset (58 total runs analyzed).
- **Core Results Table:**
  - Decision Accuracy: **75.9%** (across complex namesake and multi-flag cases).
  - False Positive Rate: **0%** (clean individuals never wrongly escalated).
  - Injection Success Rate: **0.0%** (zero breaches under active guardrails).
  - Mean Latency: **0.228 seconds** per case.
  - Mean Cost: **$0.000589 USD** per onboarding.

---

## Slide 9: Benchmark Plots & Statistical Rigor
- **Key Message:** Statistically validated performance across modes and patterns.
- **Visuals Displayed:**
  - *Runtime & Cost Boxplots:* Sequential vs Parallel; Blackboard vs Hybrid P2P.
  - *Red Flag Recall by Persona:* High resilience across all temperaments.
  - *Token Consumption Spread:* Compact context usage in Blackboard mode.
  - *Agent x Phase Latency Heatmap:* Screening crew accounts for ~75% of latency.
  - *Mann-Whitney U Test:* Proves Blackboard centralized state adds no latency penalty ($p = 0.864$).

---

## Slide 10: Observability & OpenTelemetry Provenance
- **Key Message:** One case equals one trace; every decision is cryptographically auditable.
- **Features:**
  - Deterministic 128-bit OpenTelemetry trace ID derived from `run_id`.
  - W3C `traceparent` propagation across A2A protocol.
  - Provenance audit summary linking every decision to cited `evidence_ids`.
  - Native export support for Langfuse, Phoenix, and OTLP collectors.

---

## Slide 11: Live Demonstration Walkthrough
- **Key Message:** End-to-end demonstration across the Streamlit web dashboard (`http://localhost:8501`).
- **Demo Flow (5 Minutes):**
  1. *Clean Individual (`case_001`):* Instant baseline approval (< 0.20s).
  2. *Sanctioned UBO (`case_008`):* Unravels corporate graph, detects Viktor Darkovich (45%), escalates.
  3. *Adversarial Injected Twin:* Prompt injection blocked by input guardrail; risk tier remains invariant.
  4. *Live Blackboard & Officer Console:* Live zone inspection, masked PII, and audited human override.

---

## Slide 12: Cloud Deployment & Viva Defense Readiness
- **Key Message:** Containerized, cloud-ready, and fully verified across all 11 course criteria.
- **Deployment Stack:**
  - Dockerfiles for all 5 microservices + root `docker-compose.yml`.
  - Serverless state store via Google Cloud Firestore.
  - Cloud Run deployment script with Secret Manager and `--min-instances 0` ($0 idle cost).
- **Final Status:** 98 / 98 tests passing | 0 ruff errors | 100% synthetic data | Zero hardcoded secrets.

