# 03 - Architecture and System Design

## 1. Overview

OnboardIQ is a set of cooperating services. A hierarchical ADK **Orchestrator** drives each case. A CrewAI **Screening Crew** runs behind an A2A endpoint. All agents read and write a shared **Blackboard Service** and call tools through one **MCP Tool Server**. Callbacks and OpenTelemetry provide monitoring and tracing.

```
   Client / Test Harness
          |
   +------v--------------------+
   | Streamlit UI (client form |
   | + officer review console) |
   +------+--------------------+
          | REST
   +------v------------------------------+
   | ADK  ORCHESTRATOR  (hierarchical)   |
   | + Security Gateway callbacks        |
   +--+----------+-----------+-----------+
      |          |           |
      | in-proc  | in-proc   | A2A (JSON-RPC)
 +----v---+ +----v------+ +--v----------------------------+
 | ADK    | | ADK Risk  | | CREWAI SCREENING SERVICE      |
 | Doc    | | + Review  | |  Identity Verifier            |
 | Extract| | + Client  | |  Sanctions/PEP Screener       |
 |        | | Comms     | |  Adverse Media Analyst        |
 +----+---+ +-----+-----+ |  UBO Analyst                  |
      |           |       +---------------+---------------+
      | MCP       | MCP                   | MCP
 +----v-----------v-----------------------v---------------+
 |                 MCP TOOL SERVER (FastMCP)               |
 | doc_ocr registry_lookup sanctions_screen news_search    |
 | risk_model_predict policy_rag ubo_graph blackboard_*    |
 +----+---------------------------------------------+------+
      |                                             |
 +----v------------------------+        +-----------v------------+
 | BLACKBOARD SERVICE          |        | Langfuse / OTel traces |
 | FastAPI + Firestore (or     |        | + audit log            |
 | SQLite for local dev)       |        +------------------------+
 +-----------------------------+
```

## 2. Components

| Component | Framework / tech | Responsibility |
|---|---|---|
| Blackboard Service | FastAPI + Firestore (SQLite locally) | Zoned, versioned, append-only shared state; access control by `agent_id`; event log |
| MCP Tool Server | FastMCP | Hosts all tools; both frameworks connect as MCP clients |
| Orchestrator | ADK custom workflow agent | Hierarchical control: phase advance, pattern selection (sequential or parallel), RFI loop, escalation, report assembly |
| Security Gateway | ADK callbacks plus small agent | Input and document-text scanning, PII masking, writes `pii_vault` and `intake` |
| Document Extraction Agent | ADK LlmAgent (multimodal if needed) | OCR, field extraction, tamper score |
| Screening Crew | CrewAI crew behind A2A | Identity Verifier, Sanctions/PEP Screener, Adverse Media Analyst, UBO Analyst |
| Risk Scoring Agent | ADK LlmAgent plus ML tool | Score, tier, factors, decision draft |
| Compliance Reviewer | ADK LlmAgent plus RAG tool | Policy checks and challenges; triggers revision |
| Client Communicator | ADK LlmAgent | Drafts RFI messages, handles abusive clients safely |
| Telemetry | Callbacks, OpenTelemetry, Langfuse | `StepTrace` records, traces, cost tracking |
| UI | Streamlit | Client form, live board view, officer console, results dashboard |
| Eval Runner | Python scripts | Sweeps configurations, collects reports, produces plots |

## 3. Agent registry (agent_id)

| agent_id | Framework | Reads zones | Writes zones |
|---|---|---|---|
| `adk.gateway` | ADK | raw input | `intake`, `pii_vault`, `system` |
| `adk.orchestrator` | ADK | all except `pii_vault` | `risk` (phase), `review` (final), `system` |
| `adk.extractor` | ADK | `intake`, `pii_vault` | `verification` (fields), `intake` (documents) |
| `crewai.identity_verifier` | CrewAI | `intake`, `verification`, `pii_vault` | `verification` |
| `crewai.sanctions_screener` | CrewAI | `intake` (masked) | `screening` |
| `crewai.media_analyst` | CrewAI | `intake` (masked) | `screening` |
| `crewai.ubo_analyst` | CrewAI | `intake`, `verification` | `screening` |
| `adk.risk_scorer` | ADK | all except `pii_vault` | `risk` |
| `adk.reviewer` | ADK | all except `pii_vault` | `review` |
| `adk.comms` | ADK | `intake` (masked), `review` | `system` (RFI) |

The Blackboard Service enforces this table. A request outside it returns 403 and emits an `access_denied` guardrail event.

## 4. Messaging modes (criterion 1)

- **Mode A, Blackboard-centric:** agents never message each other. Each reads the board, writes its result, and the orchestrator advances the phase. Hand-offs happen only through board entries.
- **Mode B, Hybrid P2P:** upstream results are also sent directly to the next agent over A2A or in-process calls. The board still stores state and the audit log but is not the live hand-off channel.

Both modes must produce identical report schemas so results are comparable. Implement as a `MessagingStrategy` interface with two implementations, selected by `RunConfig.mode`.

## 5. Execution patterns (criterion 4)

| Pattern | Flow |
|---|---|
| Hierarchical (always the wrapper) | Orchestrator coordinates worker agents and owns termination |
| Sequential | extract -> verify -> screen -> media -> (UBO) -> risk -> review |
| Parallel | extract -> [verify, screen, media, UBO] concurrently -> join -> risk -> review |
| Reflection | reviewer challenges draft; risk scorer revises; max 2 loops |

## 6. Case lifecycle (sequence)

1. Client submits; UI calls Orchestrator `POST /cases`.
2. Gateway scans text and OCR output, masks PII, writes `intake` and `pii_vault`, logs guardrail events. Abort with `security_abort` if blocked.
3. Extractor runs `doc_ocr`, writes `DocumentRecord` and `ExtractedField` items. If fields missing: Comms drafts an RFI (max 2 rounds).
4. Orchestrator dispatches screening: sequentially or in parallel, over A2A to the CrewAI service. Results are written to the board by the crew's agents (through MCP blackboard tools) and returned as A2A artifacts.
5. Risk Scorer reads the board, calls `risk_model_predict`, computes factors, writes `RiskAssessment` and `DecisionDraft`.
6. Reviewer runs `policy_rag`, writes `PolicyCheck` and `Challenge` items; loops back if unresolved.
7. Orchestrator applies decision rules: LOW and no flags -> approve; MEDIUM -> approve with enhanced monitoring or request info; HIGH or sanctions/PEP true or likely -> escalate to human. Never auto-reject.
8. Orchestrator assembles `OnboardingReport` from the board, validates, exports JSON and Markdown.

## 7. Blackboard Service design

- **API:** `POST /runs`, `GET /runs/{run_id}`, `GET /runs/{run_id}/zones/{zone}`, `POST /runs/{run_id}/events` (append), `GET /runs/{run_id}/events`.
- **Auth:** each caller sends an `agent_id` (and a shared service token). The service checks the access table in section 3.
- **Concurrency:** every write includes `expected_version`; a mismatch returns 409 and the client re-reads and retries. This lets parallel agents write safely.
- **Event log:** every write is stored as an immutable event `{event_id, run_id, agent_id, zone, op, payload, timestamp, version}`. The current state is a fold over events. This is the audit trail.
- **Schema:** zone payloads validate against `src/onboardiq/schema.py`.
- **Storage:** SQLite file for local development, Firestore in the cloud, behind a small repository interface.

## 8. MCP tool server design

All tools return Pydantic-validated JSON. Tools are deterministic where possible.

| Tool | Input -> Output | Implementation |
|---|---|---|
| `doc_ocr` | doc_id -> text, fields, tamper_score | pytesseract or PDF text, simple error-level or metadata tamper heuristic |
| `registry_lookup` | id_number -> record or none | SQLite mock registry |
| `sanctions_screen` | name, country -> candidates with scores | RapidFuzz over public OFAC/UN list names plus PEP list |
| `news_search` | masked query -> items | Search API, or local news corpus for reproducible runs |
| `risk_model_predict` | features -> probability high | scikit-learn gradient boosting trained on synthetic data |
| `policy_rag` | query -> policy clauses | Embedding search over a short KYC policy markdown file |
| `ubo_graph` | entity -> owners and paths | NetworkX |
| `blackboard_read` / `blackboard_write` | zone ops | Calls Blackboard Service with caller `agent_id` |

CrewAI connects through its MCP adapter; ADK through its MCP toolset. Check the current docs for exact class names.

## 9. Configuration

Environment variables (create `.env`, never commit):

```
GOOGLE_API_KEY=            # Gemini access for ADK and CrewAI (or your chosen provider key)
MODEL_NAME=                # small, cheap model for sweeps
BLACKBOARD_URL=http://localhost:8001
BLACKBOARD_TOKEN=
MCP_SERVER_URL=http://localhost:8002/mcp
CREWAI_A2A_URL=http://localhost:8003
NEWS_API_KEY=              # optional; local corpus used if empty
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=
```

`RunConfig` (Pydantic): `case_id`, `mode`, `pattern`, `reasoning`, `persona`, `seed`, `guardrails_enabled`.

## 10. Telemetry design

- Every ADK callback and CrewAI step/task callback creates a `StepTrace` (agent, phase, step type, latency, tokens, cost, error) and writes it to the `system` zone.
- OpenTelemetry spans wrap agent runs, model calls, tool calls and A2A calls. `run_id` is the trace ID so one case is one trace.
- The eval runner reads traces from the board to build heatmaps: agent x phase (latency), agent x step type (count), agent x errors and guardrail triggers.

## 11. Repository layout

```
onboardiq/
  AGENTS.md  README.md  requirements.txt  .env.example  .gitignore
  docs/                      <- these documents
  src/onboardiq/
    schema.py                <- shared Pydantic contract
    config.py                <- RunConfig, settings
    blackboard/
      service.py             <- FastAPI app
      store.py               <- SQLite and Firestore repositories
      client.py              <- thin client used by agents and tools
    mcp_server/
      server.py              <- FastMCP app
      tools/                 <- one file per tool
    agents/
      adk/                   <- gateway.py orchestrator.py extractor.py risk.py reviewer.py comms.py
      crewai/                <- screening_crew.py a2a_server.py
    messaging/               <- strategy.py (blackboard vs hybrid_p2p)
    guardrails/              <- input_guard.py pii_guard.py output_guard.py
    telemetry/               <- callbacks.py tracing.py cost.py
    eval/                    <- dataset_gen.py runner.py metrics.py plots.py
    ui/app.py                <- Streamlit
  data/                      <- synthetic cases, lists, registry.db, policy.md (generated or downloaded)
  tests/
  deploy/                    <- Dockerfile per service, cloudrun.md
```

## 12. Deployment

Google Cloud Run, one container per service: `blackboard-svc`, `mcp-tools`, `screening-crewai`, `orchestrator-adk`, `ui`. Secrets in Secret Manager. Firestore for blackboard storage. Langfuse cloud or self-hosted for traces. A GitHub Actions workflow is optional; manual `gcloud run deploy` is fine for the course.

## 13. Key design decisions

| Decision | Reason |
|---|---|
| Blackboard as a separate service | Agents run in different processes and frameworks; local memory cannot be shared |
| Zones plus masked profile | Data minimisation; adverse-media agent cannot see ID numbers |
| Append-only event log | Auditability and provenance |
| Human escalation, no auto-reject | Accountability; fuzzy matches create false positives |
| Deterministic tools, low-temperature agents | Reproducible evaluation runs |
| Two modes x two patterns | Gives a controlled comparison for criteria 1, 4 and 10 |
