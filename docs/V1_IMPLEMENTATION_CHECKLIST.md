# OnboardIQ — v1 Implementation Checklist & Milestone Roadmap

> **Target Release:** v1 (Professor Evaluation Threshold)  
> **Course:** CSE3101 Agentic AI  
> **Rule:** Implement tasks in strict sequence. After each task: run acceptance tests, report results, tick the box, commit, and push to GitHub.

---

## Phase 1: Environment & Framework Integration Foundations

- [x] **Task 1.1: Virtual Environment & Framework Dependency Verification**
  - **Objective:** Establish clean Python 3.11 `.venv` with compatible, verified releases of `crewai`, `google-adk` (and/or `google-genai`), `fastmcp`, `pydantic>=2`, `pytest`, and `ruff`.
  - **Acceptance Check:** `.venv\Scripts\python -c "import crewai, fastmcp, pydantic; print('Core frameworks loaded')"` exits 0; pytest runs cleanly.
  - **Git Commit:** `chore(env): initialize v1 virtual environment with crewai, adk, and fastmcp`

- [ ] **Task 1.2: CrewAI Blackboard Integration Function / Tool**
  - **Objective:** Create a dedicated, typed CrewAI custom tool (`BlackboardCrewTool`) enabling CrewAI agents to read from and write to the zoned Blackboard Service with optimistic locking and Pydantic payload validation.
  - **Acceptance Check:** CrewAI agent successfully executes a task that reads `intake` zone and writes an `IdentityCheck` to the `verification` zone of the blackboard.
  - **Git Commit:** `feat(crewai): implement typed blackboard integration tool for crewai agents`

- [ ] **Task 1.3: Real MCP Client Transport for External Tools**
  - **Objective:** Replace direct Python module imports of tool functions in agents with genuine FastMCP client invocations for at least two external capabilities (`registry_lookup` and `sanctions_screen`).
  - **Acceptance Check:** Integration test proving tools are executed across the FastMCP protocol interface rather than local function dispatch.
  - **Git Commit:** `feat(mcp): wire agents to invoke tools through official FastMCP client protocol`

---

## Phase 2: Authentic Framework Agents & A2A Interoperability

- [ ] **Task 2.1: Real CrewAI Screening Crew Implementation**
  - **Objective:** Refactor screening agents (`crewai.identity_verifier` and `crewai.sanctions_screener`) to instantiate authentic `crewai.Agent`, `crewai.Task`, and `crewai.Crew` objects with MCP tools and blackboard tools.
  - **Acceptance Check:** Standalone CrewAI execution on a benchmark applicant case successfully populates blackboard verification and screening zones.
  - **Git Commit:** `feat(crewai): implement authentic CrewAI screening crew with real Agent and Task classes`

- [ ] **Task 2.2: Real Google ADK Agents Implementation**
  - **Objective:** Refactor ADK components (`adk.risk_scorer`, `adk.reviewer`, `adk.orchestrator`) to use genuine Google ADK / Google GenAI SDK constructs with structured prompt definitions and callback hooks.
  - **Acceptance Check:** ADK risk scorer and reviewer execute reasoning with structured Pydantic outputs and tool validation.
  - **Git Commit:** `feat(adk): implement authentic Google ADK agents for risk scoring and compliance review`

- [ ] **Task 2.3: Agent-to-Agent (A2A) Protocol Communication**
  - **Objective:** Connect the Google ADK Orchestrator and the CrewAI Screening Crew via the A2A discovery protocol (`/.well-known/agent.json` Agent Card) and JSON-RPC task delegation.
  - **Acceptance Check:** ADK agent fetches the CrewAI Agent Card, triggers remote screening over A2A, receives structured response artifacts, and logs an `a2a` StepTrace.
  - **Git Commit:** `feat(a2a): establish interoperable A2A communication between ADK orchestrator and CrewAI crew`

---

## Phase 3: Agentic Design Patterns & Comparative Architecture

- [ ] **Task 3.1: Multi-Agent Design Patterns (Hierarchical, Parallel, Sequential, Reflection)**
  - **Objective:** Implement and benchmark the four core agentic patterns:
    1. Hierarchical supervisor controlling worker sub-agents (`adk.orchestrator`).
    2. Parallel concurrent worker execution of screening sub-tasks.
    3. Sequential pipeline execution.
    4. Closed reflection loop between `adk.reviewer` and `adk.risk_scorer` (max 2 cycles).
  - **Acceptance Check:** Tests demonstrate correct execution flow and latency reduction in parallel pattern vs sequential.
  - **Git Commit:** `feat(patterns): implement hierarchical, parallel, sequential, and reflection agentic patterns`

- [ ] **Task 3.2: Comparative Architecture: Blackboard vs Peer-to-Peer (P2P)**
  - **Objective:** Implement both Blackboard Architecture (Mode A) and Direct P2P Architecture (Mode B) in `MessagingStrategy`. Run identical benchmark cases through both modes to compare state transfer latency, data isolation, and message complexity while ensuring identical `OnboardingReport` schema.
  - **Acceptance Check:** Comparative test script runs both modes on identical cases, asserts identical output schema, and logs comparative telemetry.
  - **Git Commit:** `feat(messaging): implement comparative benchmark between blackboard and p2p messaging`

---

## Phase 4: Security Guardrails, Prompt Variances & Telemetry

- [ ] **Task 4.1: Security Guardrails & Callbacks**
  - **Objective:** Implement multi-tier guardrails:
    1. Input Guard: regex and semantic detection of prompt injection, toxic language, and social engineering.
    2. PII Guard: blocks unmasked PAN, Passport, DOB, or street addresses from escaping to outbound tools.
    3. Output Guard & Callbacks: type validation of tool returns, and strict enforcement that high-risk cases cannot be auto-rejected (must escalate).
  - **Acceptance Check:** Security test suite verifies blocked injection attempts, zero PII tool leakage, and forced escalation on high-risk cases.
  - **Git Commit:** `feat(guardrails): enforce input scanning, PII vault isolation, and output callbacks`

- [ ] **Task 4.2: Prompt Variances (ReAct vs Few-Shot) & Adversarial Personas**
  - **Objective:** Implement prompt variance handling in agents (ReAct thought-action-observation structure vs Few-Shot template) and test against 5 adversarial applicant personas (cooperative, impatient, abusive, forger, injecting).
  - **Acceptance Check:** Evaluation shows prompt variances induce observable reasoning differences while active guardrails prevent injection attacks from modifying the risk tier.
  - **Git Commit:** `feat(prompts): add ReAct vs few-shot prompt variances and adversarial persona injector`

- [ ] **Task 4.3: Task Monitoring & Distributed OpenTelemetry Tracing**
  - **Objective:** Emit strongly typed `StepTrace` events on every agent step and hook into OpenTelemetry to ensure 1-case-1-trace provenance with W3C `traceparent` propagation across A2A.
  - **Acceptance Check:** Full case execution generates a complete trace tree with root case span and child agent/tool spans visible in telemetry.
  - **Git Commit:** `feat(telemetry): wire StepTrace callbacks and distributed OpenTelemetry tracing`

---

## Phase 5: End-to-End Evaluation & Cloud Deployment

- [ ] **Task 5.1: End-to-End Performance Evaluation & Analytics**
  - **Objective:** Execute an automated multi-run evaluation sweep across cases, patterns (sequential vs parallel), modes (blackboard vs P2P), and prompt variants. Generate latency and cost estimates, summary statistics, boxplots, and heatmaps.
  - **Acceptance Check:** Sweep outputs `results/metrics.csv`, runtime boxplots, and latency/phase heatmaps with statistical significance testing.
  - **Git Commit:** `feat(eval): execute end-to-end performance evaluation sweep with statistical plots`

- [ ] **Task 5.2: Cloud Platform Deployment Verification**
  - **Objective:** Validate containerization across all services (`blackboard-svc`, `mcp-tools`, `screening-crewai`, `ui`) via Docker Compose, and verify the step-by-step Google Cloud Run deployment checklist.
  - **Acceptance Check:** `docker compose build` succeeds with zero errors, and `deploy/cloudrun.md` commands validate against GCP deployment requirements.
  - **Git Commit:** `feat(deploy): verify multi-service Docker composition and Cloud Run deployment bundle`

