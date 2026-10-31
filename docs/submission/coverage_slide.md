# OnboardIQ — Project 2 Coverage Slide Content (Milestone M1)

*This document contains the slide-ready content table for the single coverage slide required for the November 6 submission. Statuses reflect verifiable code in the repository as of November 1, 2026.*

---

## OnboardIQ: Coverage Against 11 Course Criteria

| # | Course Criterion | Status | Evidence (File, Command, or Artifact) | Next Step |
|---|---|---|---|---|
| **1** | **Blackboard & Messaging Architecture** | **Done** | `src/onboardiq/blackboard/` (FastAPI app, SQLite store); `tests/test_blackboard.py` (6 passed); `src/onboardiq/messaging/strategy.py` (Blackboard & Hybrid P2P modes validated in `tests/test_modes_and_patterns.py`). | Extend blackboard event stream to live WebSockets in UI. |
| **2** | **At Least Two MCP Tools** | **Done** | `src/onboardiq/mcp_server/server.py` exposing 5 tools (`registry_lookup`, `sanctions_screen`, `doc_ocr`, `ubo_graph`, `risk_predict`); `tests/test_mcp_server.py` (7 passed). | Add `policy_rag` and `news_search` tools in T23 & T24. |
| **3** | **Pydantic Structured Output** | **Done** | `src/onboardiq/schema.py` enforcing Pydantic v2 validation on `OnboardingReport`, `DecisionDraft`, `Blackboard`, and `EvidenceRef`; `tests/test_schema.py` (20 passed). | Add policy compliance challenge schemas in T24. |
| **4** | **Agentic Design Patterns & Comparison** | **Done** | Sequential and Parallel patterns implemented in `agents/adk/orchestrator.py`; verified identical schema and compared in `tests/test_parallel.py` and `results/plots/runtime_by_pattern.png`. | Add Compliance Reviewer reflection loop in T24. |
| **5** | **Callbacks, Monitoring & Heatmap** | **Done** | `src/onboardiq/telemetry/callbacks.py` writing `StepTrace` to `system.traces`; `scripts/show_traces.py`; heatmap generated at `results/plots/agent_phase_heatmap.png`. | Connect trace events to OpenTelemetry span collectors in T29. |
| **6** | **A2A Interoperability** | **Done** | `src/onboardiq/agents/crewai/a2a_server.py` publishing Agent Card at `/.well-known/agent.json`; ADK calls CrewAI over A2A; verified in `tests/test_a2a.py`. | Add bidirectional A2A communication for reviewer challenges. |
| **7** | **Framework Compliance (CrewAI & ADK Only)** | **Done** | Verified via `pyproject.toml` and codebase audit: only `google-adk` and `crewai` used; zero LangChain, LangGraph, AutoGen, or LlamaIndex imports. | Maintain framework boundary across all final phase agents. |
| **8** | **Guardrails & Security** | **Done** | `src/onboardiq/guardrails/`: `input_guard.py` (injection/toxicity), `pii_guard.py` (outbound leak block), `output_guard.py` (no auto-reject); 5 tests in `tests/test_security_guardrails.py`. | Add adversarial persona injection test suite in T27. |
| **9** | **Observability & Provenance** | **In progress** | Every finding links resolvable `evidence_ids` in `schema.py`; per-agent latency/cost in `system.traces`. End-to-end trace per case functional. | Integrate OpenTelemetry export to Langfuse/Phoenix in T29. |
| **10** | **Evaluation Suite (Runs, Plots, Dataset)** | **In progress** | 10 benchmark cases in `data/cases/`; 10/10 runs completed in `results/metrics.csv` (100% accuracy); runtime boxplot and heatmap generated. | Expand dataset to 24 cases and execute full 40+ grid sweep in T30. |
| **11** | **Cloud Deployment** | **Planned** | Local deployment active via Uvicorn (FastAPI :8001) and Streamlit (:8501); deployment architecture designed in `docs/03_ARCHITECTURE.md` Section 9. | Containerize services with Dockerfiles and deploy to Google Cloud Run in T32. |

---

### Slide Layout Recommendation:
- **Title:** OnboardIQ — Milestone M1 Coverage & Implementation Progress
- **Summary Metric Callout Boxes:**
  - **8/11 Criteria Done** (73% Complete at Milestone M1)
  - **2/11 Criteria In Progress** (Observability, 40+ Evaluation Sweep)
  - **1/11 Planned** (Google Cloud Run Deployment)
  - **62 Unit Tests Passing** | **0 Lint Warnings** | **100% Benchmark Accuracy**

