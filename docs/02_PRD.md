# 02 - Product Requirements Document (PRD)

## 1. Product summary

OnboardIQ takes a client application (form data plus documents) and returns a structured `OnboardingReport`: decision, risk tier and score, red flags, evidence trail, security events and per-agent metrics. High-risk cases are escalated to a human officer through a review console.

## 2. Users and key scenarios

| User | Scenario |
|---|---|
| Client (simulated) | Submits an application with documents. May be cooperative, impatient, abusive, forging, or injecting. |
| Onboarding analyst | Watches a case progress on the live blackboard view. |
| Compliance officer | Reviews escalated cases, reads evidence and rationale, approves or rejects. |
| Evaluator (instructor) | Runs or inspects the evaluation sweep and traces. |

## 3. Functional requirements

Priority: **P0** = needed for the Nov 6 demo, **P1** = needed for final phase, **P2** = nice to have.

### 3.1 Intake and security gateway
- **FR-01 (P0)** Accept an application (individual or company) as an `Applicant` plus uploaded documents.
- **FR-02 (P0)** Scan client text and OCR text for toxicity, social engineering and prompt injection; log a `GuardrailEvent` for each scan.
- **FR-03 (P0)** Separate raw PII into the `pii_vault` zone and expose only a `MaskedProfile` to other agents.

### 3.2 Document extraction
- **FR-04 (P0)** Extract typed fields with confidence from synthetic ID, address proof, and (for companies) incorporation certificate.
- **FR-05 (P1)** Produce a tamper score per document.
- **FR-06 (P1)** If documents are missing or low confidence, draft a polite request for information, maximum 2 rounds.

### 3.3 Verification and screening
- **FR-07 (P0)** Cross-check name, DOB, address between declared data, documents and the mock registry; write `IdentityCheck` records.
- **FR-08 (P0)** Fuzzy-screen names against sanctions and PEP lists and classify each hit (true, likely, false positive, unresolved).
- **FR-09 (P1)** Search for adverse media and judge relevance to the specific person.
- **FR-10 (P1)** For companies, build an ownership graph, identify owners above 10 percent, and screen each.

### 3.4 Risk, review, decision
- **FR-11 (P0)** Compute a 0 to 100 risk score and LOW, MEDIUM or HIGH tier from an ML model plus rule factors, with per-factor contribution and evidence IDs.
- **FR-12 (P0)** Draft a decision (`DecisionDraft`) citing evidence.
- **FR-13 (P1)** Compliance reviewer checks policy rules and raises challenges; unresolved challenges force a revision (maximum 2 loops).
- **FR-14 (P0)** Escalate to a human for HIGH tier or any true or likely sanctions or PEP hit. The system must never auto-reject.
- **FR-15 (P1)** Provide a review console where the officer sees evidence and records a decision.

### 3.5 Output
- **FR-16 (P0)** Produce `OnboardingReport` as validated JSON and a Markdown summary.

### 3.6 Platform capabilities (course criteria)
- **FR-17 (P0)** Shared blackboard service with zones, access control, versioning and an append-only event log.
- **FR-18 (P0)** Two messaging modes: Blackboard-centric and Hybrid P2P, selectable by configuration.
- **FR-19 (P0)** Two execution patterns: Sequential and Parallel, selectable by configuration, under a hierarchical orchestrator.
- **FR-20 (P0)** ADK orchestrator communicates with the CrewAI screening crew over A2A with published Agent Cards.
- **FR-21 (P0)** All tools served by an MCP server and used by both frameworks.
- **FR-22 (P0)** Callbacks in both frameworks emit `StepTrace` records.
- **FR-23 (P1)** Tracing to Langfuse or Phoenix via OpenTelemetry with one trace per case.
- **FR-24 (P1)** Evaluation runner executing 40 or more configured runs and producing metrics, boxplots, heatmaps.
- **FR-25 (P1)** Deployment of all services to Google Cloud Run.

## 4. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-01 | Security: no raw PII in outbound tool queries, logs shown in the UI, or the report. |
| NFR-02 | Auditability: every conclusion has resolvable `evidence_ids`; blackboard log is append-only. |
| NFR-03 | Reliability: schema validation with up to 2 retries; a failed run records the error rather than crashing the sweep. |
| NFR-04 | Performance: a single case completes in under 3 minutes in parallel mode with the chosen model (target, to be measured). |
| NFR-05 | Cost: report cost per run; target under a few US cents per case with a small model (to be measured). |
| NFR-06 | Reproducibility: fixed random seeds for dataset generation, temperature 0 to 0.2 for agents, deterministic tools. |
| NFR-07 | Maintainability: typed code, tests for guardrails, schema, metrics and dataset generator. |
| NFR-08 | Explainability: each risk factor and decision rationale is human-readable. |

## 5. Mapping to the 11 minimum criteria

| # | Course criterion | Requirements | Verified by |
|---|---|---|---|
| 1 | Blackboard and messaging architecture | FR-17, FR-18 | Both modes run; board log shows handoffs |
| 2 | At least two MCP tools | FR-21 | Tool calls visible in traces |
| 3 | Pydantic structured output | FR-16 | Report validates against schema |
| 4 | Agentic design patterns and comparison | FR-19, FR-13 | Sequential vs parallel results; reflection loop |
| 5 | Callbacks and monitoring, heatmap | FR-22 | Heatmap generated from `StepTrace` |
| 6 | A2A interoperability | FR-20 | Agent Cards and live A2A call logged |
| 7 | Only CrewAI and ADK | AGENTS.md rule | Code review |
| 8 | Guardrails and security | FR-02, FR-03, FR-14, NFR-01 | Persona runs show blocks; ablation |
| 9 | Observability and provenance | FR-23, NFR-02 | Trace per case; evidence chain |
| 10 | 40+ runs, boxplots, dataset | FR-24 | Results folder with plots |
| 11 | Cloud deployment | FR-25 | Live URL |

## 6. Acceptance criteria (high level)

1. **Happy path:** clean individual applicant is auto-approved with LOW tier and a complete evidence trail.
2. **Company path:** company with a two-level ownership chain resolves the owners and screens them.
3. **Sanctions near-match:** a perturbed sanctioned name is escalated to a human, not auto-approved or auto-rejected.
4. **Namesake false positive:** a clean applicant with a similar name to a listed person is classified false positive with reasoning.
5. **Forger:** tampered or inconsistent document raises a red flag and triggers a request for information or escalation.
6. **Abusive client:** toxic message is blocked or neutralised, the process continues politely, and no case details leak.
7. **Injection:** hidden instruction in a document does not change the risk tier; a `prompt_injection` event is logged.
8. **PII control:** a unit test proves outbound `news_search` queries containing ID numbers are blocked.
9. **Modes and patterns:** same case runs in all four combinations (2 modes x 2 patterns) and produces valid reports.
10. **Evaluation:** a sweep of at least 40 runs completes and produces boxplots and heatmaps.

## 7. Release scope

- **Milestone M1 (Nov 6 demo, P0):** schema, blackboard, MCP server with registry, sanctions and OCR tools, ADK orchestrator and extraction, CrewAI screening crew over A2A, risk scoring, basic guardrails, callbacks, first runs.
- **Milestone M2 (final phase, P1):** adverse media, UBO, reviewer loop, tamper score, review console, tracing, full 40-run sweep, deployment.
- **Stretch (P2):** more personas, local LLM variant for privacy, richer UI.
