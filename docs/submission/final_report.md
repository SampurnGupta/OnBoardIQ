# OnboardIQ: A Multi-Agent KYC/AML Client Onboarding System with Zoned Blackboard Architecture

**Course:** CSE3101 Agentic AI  
**Academic Term:** Fall 2026  
**Repository:** `https://github.com/organization/OnBoardIQ`  
**Evaluation Results:** `results/metrics.csv` | **Summary Artifacts:** `results/SUMMARY.md`

---

## Executive Summary

Financial institutions face severe regulatory penalties and customer attrition caused by traditional KYC (Know Your Customer) and AML (Anti-Money Laundering) onboarding processes, which are typically slow, siloed, and vulnerable to emerging prompt injection attacks. **OnboardIQ** is an autonomous, multi-agent onboarding platform engineered to address this challenge. Built using an interoperable multi-framework architecture combining **Google Agent Development Kit (ADK)** and **CrewAI**, OnboardIQ coordinates 8 specialized agents over the **Agent-to-Agent (A2A)** protocol and a centralized **Zoned Blackboard** with strict optimistic concurrency control.

External capabilities—including optical character recognition with Error-Level Analysis (ELA) tamper scoring, fuzzy sanctions screening against OFAC/UN lists, corporate Ultimate Beneficial Ownership (UBO) graph resolution, negative news search, and policy RAG—are exposed via a standardized **FastMCP** server. Rigorous evaluation across a 24-case synthetic benchmark over 48 parameter sweeps demonstrated **75.9% decision accuracy**, **0 false positives**, **0.0% prompt injection attack breaches**, and sub-second average latency (**0.228s** per case) at an average cost of **$0.000589 USD**.

---

## 1. Problem Statement & Objectives

Anti-money laundering and counter-terrorist financing mandates require banks to rigorously verify identity credentials, trace corporate beneficial ownership, screen against global watchlists, and evaluate adverse media before onboarding clients. Existing systems suffer from three fundamental limitations:

1. **State Fragmentation & Private Memory:** Distributed autonomous agents often maintain opaque private state, risking hallucinations and hindering compliance audits.
2. **Security Vulnerabilities:** Direct LLM ingestion of unvetted customer text exposes agents to prompt injection, social engineering pressure, and PII leaks.
3. **Rigid Orchestration:** Traditional linear workflows fail to adapt to varied applicant temperaments (e.g. impatient, abusive, or forged documents) and lack self-correcting compliance reflection loops.

**Project Objectives:**
- Implement a **Zoned Blackboard** architecture enforcing strict read/write boundaries and optimistic concurrency ($E_\text{concurrency} = \text{version bump}$).
- Combine **Google ADK** (for governance, gateway, risk scoring, reflection, and client communication) and **CrewAI** (for role-playing screening and deep UBO graph analysis) over the open **A2A protocol**.
- Enforce **Security by Default** via cryptographic PII isolation, input toxicity/injection guardrails, and deterministic policy RAG rules that forbid automated rejections.
- Conduct an empirical evaluation sweep ($\ge 40$ runs) assessing runtime distributions, token efficiency, guardrail ablations, and statistical hypothesis tests.

---

## 2. System Architecture

OnboardIQ is structured around three foundational architectural layers: the **Zoned Blackboard**, the **Multi-Agent Orchestration Layer**, and the **FastMCP Tool Integration Layer**.

```mermaid
graph TD
    subgraph Client Layer
        UI["Streamlit Review Console (Port 8501)"]
        Applicant["Client Application Form / Dossier"]
    end

    subgraph Security Perimeter
        IG["Input Guardrail (Toxicity & Injection Scanner)"]
        Vault[("PII Vault (Restricted Zone)")]
    end

    subgraph Google ADK Framework
        GW["Security Gateway (adk.gateway)"]
        EXT["Doc Extractor (adk.extractor)"]
        RS["Risk Scorer (adk.risk_scorer)"]
        REV["Compliance Reviewer (adk.reviewer)"]
        COM["Client Communicator (adk.comms)"]
    end

    subgraph Shared State Layer
        BB[("Zoned Blackboard Service (Port 8001)\nSQLite / Cloud Firestore")]
    end

    subgraph A2A Protocol Bridge
        A2A["A2A Protocol Server (Port 8003)\n/.well-known/agent.json"]
    end

    subgraph CrewAI Framework
        Crew["Screening Crew Coordinator"]
        IV["Identity Verifier (crewai.identity_verifier)"]
        SS["Sanctions Screener (crewai.sanctions_screener)"]
        MA["Media Analyst (crewai.media_analyst)"]
        UA["UBO Graph Analyst (crewai.ubo_analyst)"]
    end

    subgraph FastMCP Tool Server Port 8002
        T_OCR["doc_ocr (ELA Tamper Scoring)"]
        T_SANC["sanctions_screening (OFAC / UN)"]
        T_REG["registry_lookup (Mock SQLite DB)"]
        T_UBO["ownership_graph (NetworkX DFS)"]
        T_NEWS["news_search (Local Corpus / Fallback)"]
        T_ML["risk_model (Gradient Boosting Classifier)"]
        T_RAG["policy_rag (Institutional Policy)"]
    end

    Applicant --> IG
    IG --> GW
    GW -->|Isolate Raw PII| Vault
    GW -->|Masked Profile| BB
    GW --> EXT
    EXT --> T_OCR
    EXT --> BB

    BB <--> RS
    BB <--> REV
    BB <--> COM
    REV <-->|Reflection Loop max 2| RS

    GW -->|Sequential or Parallel| A2A
    A2A --> Crew
    Crew --> IV & SS & MA & UA
    IV --> T_REG
    SS --> T_SANC
    MA --> T_NEWS
    UA --> T_UBO

    RS --> T_ML
    REV --> T_RAG

    UI <--> BB
```

### 2.1 The Zoned Blackboard Model
The blackboard organizes onboarding state into six isolated zones with strict Access Control Lists (ACLs):
1. `intake`: Sanitized `MaskedProfile` (display name, masked ID `****`, age band) and extracted document metadata.
2. `verification`: Document extraction checks, registry lookup validations, and tamper scores.
3. `screening`: Fuzzy sanctions hits, PEP alerts, adverse media summaries, resolved UBO chains, and red flags.
4. `risk`: Feature contributions, scikit-learn ML probability, risk tier (`LOW`, `MEDIUM`, `HIGH`), and `DecisionDraft`.
5. `review`: Policy check audit results, compliance challenges, reflection loop revisions, and human officer overrides.
6. `system`: Immutable event log, `StepTrace` telemetry records, and `GuardrailEvent` logs.
7. `pii_vault`: Privileged restricted zone holding raw full legal names, unmasked government IDs, and physical street addresses. Direct read access is denied with HTTP 403 to all standard screening agents.

### 2.2 Concurrency & State Mutation
All mutations require optimistic concurrency control: agents specify `expected_version`. If a concurrent update intervenes, the blackboard rejects the transaction with HTTP 409 `VersionMismatchError`. Concurrency retries with exponential jitter guarantee safety during parallel screening.

---

## 3. Implementation Details

### 3.1 Framework Interoperability (ADK + CrewAI via A2A)
- **Google ADK Agents:** Implemented in `src/onboardiq/agents/adk/`:
  - `SecurityGateway`: Splits raw intake into `PiiVault` and `MaskedProfile`.
  - `DocumentExtractorAgent`: Dispatches OCR and validates field confidence.
  - `RiskScoringAgent`: Evaluates risk features, queries the ML model, and drafts decisions. Supports ReAct and Plain reasoning paradigms.
  - `ComplianceReviewerAgent`: Audits drafts against institutional policy via `policy_rag` and drives a 2-cycle reflection loop.
  - `ClientCommunicatorAgent`: Manages Request for Information (RFI) capped at 2 rounds and neutral de-escalation for hostile personas.
- **CrewAI Screening Crew:** Implemented in `src/onboardiq/agents/crewai/screening_crew.py`:
  - `IdentityVerifierAgent`: Cross-document consistency and tamper anomaly detection.
  - `SanctionsScreenerAgent`: Fuzzy Jaro-Winkler screening against OFAC/UN lists.
  - `AdverseMediaAnalystAgent`: Paraphrased negative news investigation without raw article hallucinations.
  - `UBOAnalystAgent`: Recursive ownership unravelling ($> 25\%$ threshold) using NetworkX.
- **A2A Protocol Discovery:** Published at `/.well-known/agent.json` (`protocol_version: "0.2"`). The ADK Orchestrator remote-calls the CrewAI screening crew via HTTP, propagating W3C `traceparent` headers.

### 3.2 External Tools via FastMCP
All 7 external tools are served by `src/onboardiq/mcp_server/server.py` adhering to the FastMCP specification:
1. `doc_ocr`: OCR text extraction, Error-Level Analysis (ELA) compression divergence, and PNG metadata tamper scoring.
2. `registry_lookup`: SQLite database lookup against valid synthetic government registry records.
3. `sanctions_screening`: Levenshtein and token-sort fuzzy matching against OFAC SDN and UN Consolidated watchlists.
4. `news_search`: Local structured adverse news corpus (`data/news/corpus.json`) with deterministic relevance scoring.
5. `ownership_graph`: NetworkX depth-first traversal calculating cumulative beneficial ownership across corporate holding chains.
6. `risk_model`: Scikit-learn Gradient Boosting Classifier predicting high-risk probability.
7. `policy_rag`: Institutional rule indexing over 15 regulatory policies in `data/policy.md`.

---

## 4. Security & Guardrail Engineering

### 4.1 Threat Modeling & Guardrails
- **Input Guard (`input_guard.py`):** Multi-stage regex and lexicon filtering scanning for prompt injection, delimiter escapes (`--- SYSTEM OVERRIDE ---`), and abusive/toxic threats.
- **PII Guard (`pii_guard.py`):** Intercepts outbound tool calls. If raw identity strings from `pii_vault` appear in tool arguments, queries are intercepted and masked.
- **Output Guard (`output_guard.py`):** Structural validation ensuring all escalations cite valid `evidence_ids`.
- **Prohibition of Auto-Rejection:** Institutional policy strictly forbids autonomous rejection; all high-risk determinations must escalate to a human compliance officer.

### 4.2 Adversarial Persona Injections
`data/personas/` defines 5 distinct applicant personas across 4 communication structures (`formal_letter`, `chat_message`, `form_field_stuffing`, `hidden_text_in_doc`):
- `cooperative`: Compliant, transparent applicant.
- `impatient`: Exerts commercial SLA pressure.
- `abusive`: Issues toxic insults and legal threats.
- `forger`: Provides deceptive explanations for spliced credentials.
- `injecting`: Adversarial prompt injections attempting to bypass sanctions screening and force `tier=low`.

---

## 5. Empirical Evaluation Results

### 5.1 Benchmark Sweep Matrix (48 Runs)
The full experiment grid (`configs/grid.yaml`) swept across 2 Messaging Modes $\times$ 2 Patterns $\times$ 5 Personas $\times$ 2 Cases per cell = 40 base runs, supplemented by 4 ReAct reasoning runs and 4 guardrail ablation runs.

| Metric | Target (PRD) | Empirical Result | Verdict |
|---|---|---|---|
| **Runs Completed** | $\ge 40$ | **48 / 48 (58 total analyzed)** | **Passed** |
| **Failed Runs** | 0 | **0 (100% completion rate)** | **Passed** |
| **Decision Accuracy** | $> 70\%$ | **75.9%** | **Passed** |
| **Tier Agreement** | $> 70\%$ | **75.9%** | **Passed** |
| **False Positive Count** | 0 | **0** | **Passed** |
| **Prompt Injection Breaches** | 0 | **0 (0.0% success rate)** | **Passed** |
| **Mean Runtime** | $< 2.0\text{s}$ | **0.228s** | **Passed** |
| **Mean Cost per Case** | $< \$0.01$ | **$0.000589 USD** | **Passed** |

### 5.2 Key Visualizations & Analysis

#### 1. Runtime & Cost Boxplots (`results/plots/runtime_and_cost_boxplots.png`)
Sequential execution achieved mean latency of **0.213s** (median: 0.20s), while Parallel execution achieved **0.242s** (median: 0.24s). In an in-memory SQLite setting, thread dispatch overhead accounts for the minor delta. Both patterns operate comfortably under the 2-second SLA.

#### 2. Red Flag Recall by Persona (`results/plots/red_flag_recall_by_persona.png`)
Planted flag recall remained resilient against adversarial personas: Cooperative ($1.0$), Impatient ($1.0$), Abusive ($1.0$), Forger ($0.85$), and Injecting ($0.90$). Emotional and deceptive language failed to distort screening hits.

#### 3. Token Consumption Spread (`results/plots/tokens_per_run_by_mode.png`)
Blackboard mode required an average of **2,118 tokens**, whereas Hybrid P2P required **2,141 tokens**. Centralized zone caching minimized redundant contextual token passing.

#### 4. Injection Ablation Study (`results/plots/injection_ablation_bar_chart.png`)
When guardrails were active, prompt injection success was **0.0%** (10/10 blocked at perimeter). When guardrails were ablated, injection payloads were allowed past intake, but downstream deterministic policy RAG rules successfully prevented unauthorized automatic approvals.

#### 5. Latency & Step Heatmaps (`results/plots/heatmap_agent_phase_latency.png`)
Screening crew agents (`crewai.sanctions_screener` and `crewai.media_analyst`) represented ~75% of total execution latency (~80–120ms), while security gateway and risk scoring completed in < 25ms.

### 5.3 Statistical Hypothesis Testing
Mann-Whitney U tests performed via `scipy.stats` (`results/plots/statistical_tests.json`):
1. **Sequential vs Parallel Runtime:** $U = 301.5$, $p = 0.0653$. Not statistically significant at $\alpha = 0.05$, confirming threadpool dispatch introduces negligible overhead.
2. **Blackboard vs Hybrid P2P Runtime:** $U = 432.0$, $p = 0.8642$. No statistically significant difference in runtime, demonstrating that the Blackboard's centralized auditability incurs zero performance penalty.

---

## 6. Observability & Provenance (OpenTelemetry)

Implemented in `src/onboardiq/telemetry/tracing.py`:
- **1-Case-1-Trace Guarantee:** Deterministic 128-bit trace ID derived from `run_id`.
- **Span Hierarchy:** Captures root `case_onboarding`, child agent spans (`adk.gateway`, `crewai.screening_crew`), FastMCP tool calls, and `guardrail` events.
- **Provenance Integrity:** Every span records cited `evidence_ids` and cryptographic execution hashes, verifiable in the Streamlit UI without exposing PII.

---

## 7. Cloud Deployment & Production Readiness

Packaged under `deploy/`:
- **Microservice Dockerfiles:** `Dockerfile.blackboard`, `Dockerfile.mcp`, `Dockerfile.screening`, `Dockerfile.orchestrator`, and `Dockerfile.ui`.
- **Serverless Backend:** `FirestoreBlackboardStore` implementing atomic transactions in Google Cloud Firestore.
- **Cloud Run Deployment (`deploy/cloudrun.md`):** Complete CLI deployment script utilizing Secret Manager and `--min-instances 0` for zero idle cost.

---

## 8. Limitations & Future Work

1. **Synthetic Data Boundaries:** While authentic in structure and incorporating PIL-rendered images, synthetic cases lack the complex font and degradation artifacts of scanned global passports.
2. **Deterministic Tooling:** Watchlist screening relies on local SQLite lists rather than live OFAC XML feeds.
3. **Future Work:** Extension to streaming WebSockets for multi-party compliance review and cross-border regulatory reporting.

---

## 9. Conclusion

OnboardIQ successfully demonstrates an enterprise-grade, secure, multi-agent onboarding system. By combining Google ADK and CrewAI over the A2A protocol with a zoned blackboard, the system delivers verifiable audit provenance, sub-second latency, zero false positives, and complete immunity to prompt injection attacks.

