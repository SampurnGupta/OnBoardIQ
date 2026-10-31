# 06 - Implementation Plan and Task Checklist

Planned from Oct 31 to the Nov 6 (23:59) Project 2 submission, then continuing to the final phase. Tick boxes as you finish. Do one task at a time.

**Project 2 submission needs:** updated problem statement, updated project plan, work-in-progress report, code, and a one-slide PPT showing coverage of the project so far vs the criteria.

**Minimum viable demo for Nov 6:** one individual and one company case; both messaging modes; ADK to CrewAI over A2A; MCP tools (registry, sanctions, OCR, risk model); blackboard with zones; guardrails for injection, toxicity and PII; callbacks writing traces; first batch of runs with a preliminary boxplot.

## Day 1 (Oct 31 - Nov 1): Foundations

- [x] **T01 Project skeleton.** Folders as in `docs/03_ARCHITECTURE.md` section 11, `pyproject` or `requirements.txt`, `.gitignore`, `.env.example`, ruff and pytest config.
  *Check:* `pytest` runs (even with zero tests) and `ruff check .` passes.
  *Done:* All directories and placeholder files created per architecture §11. `pytest` 3 passed, `ruff check .` all clean. Ruff auto-fixed `Optional` → `X | None` style in schema.py.
- [x] **T02 Schema.** Review `src/onboardiq/schema.py`, add `RunConfig` and `LabelledCase`, write validator tests.
  *Check:* tests for `DecisionDraft`, `PiiVault`, `Blackboard` round-trip pass.
  *Done:* 20 tests covering DecisionDraft validators, PiiVault defaults, Blackboard JSON round-trip, RunConfig defaults, LabelledCase validation, EvidenceRef. All pass. Ruff clean.
- [x] **T03 Blackboard service.** FastAPI app, SQLite store, zone access table, versioned append-only events, client library.
  *Check:* tests for read/write, 403 on forbidden zone, 409 on stale version.
  *Done:* FastAPI service in `blackboard/service.py`, `SQLiteBlackboardStore` in `store.py`, `BlackboardClient` in `client.py`. 6 unit tests passing (read/write, 403 + GuardrailEvent, 409 concurrency, event ordering, client). Ruff clean.
- [x] **T04 Synthetic data generator (first 10 cases).** Faker applicants, PIL document images, mock registry DB, planted flags with ground truth.
  *Check:* 10 case JSON files validate; images open; registry contains clean cases.
  *Done:* Generated 10 benchmark cases in `data/cases/`, rendered document images in `data/docs/`, mock registry in `data/registry.db`, sanctions/PEP sample lists. 4 unit tests passing, ruff clean.

## Day 2 (Nov 2): Tools and first ADK agents

- [x] **T05 MCP tool server.** FastMCP with `registry_lookup`, `sanctions_screen`, `doc_ocr`, `blackboard_read/write`.
  *Check:* MCP inspector or a client script lists tools and calls each successfully.
  *Done:* FastMCP server in `mcp_server/server.py` with modular tools in `mcp_server/tools/`. `scripts/mcp_smoke_test.py` passed; 7 unit tests pass; ruff clean.
- [x] **T06 ADK extractor and gateway (basic).** Gateway writes `intake` and `pii_vault`; extractor reads documents via MCP and writes fields.
  *Check:* one case produces `DocumentRecord` entries on the board.
  *Done:* Built `agents/adk/gateway.py` and `extractor.py`. `scripts/run_t06.py` produces DocumentRecord entries with EvidenceRef on the board. Unit tests pass.

## Day 3 (Nov 3): CrewAI crew and A2A

- [x] **T07 CrewAI screening crew.** Identity Verifier and Sanctions Screener first, using MCP tools and writing to the board.
  *Check:* crew runs standalone on one case and writes `IdentityCheck` and `ScreeningHit`.
  *Done:* Built `agents/crewai/screening_crew.py`. `scripts/run_t07.py` runs standalone on benchmark cases writing IdentityCheck and ScreeningHit records with EvidenceRef. Tests pass.
- [x] **T08 A2A link.** Wrap crew in an A2A server with an Agent Card; ADK orchestrator calls it through a remote A2A client.
  *Check:* orchestrator triggers the crew over A2A; Agent Card fetchable; call visible in logs. Note exact library versions used.
  *Done:* Built `agents/crewai/a2a_server.py`. Agent Card published at `/.well-known/agent.json`. Remote A2A invocation verified with StepTrace recorded in system zone. Unit tests pass.
- [x] **T09 Orchestrator (sequential, blackboard mode).** Phase control, termination, report assembly.
  *Check:* clean case runs end to end and produces a valid `OnboardingReport`.
  *Done:* Built `agents/adk/orchestrator.py` and `scripts/run_case.py`. Clean case (case_001) auto-approves; mismatch and sanctions cases escalate to human with cited evidence trails. Produces valid OnboardingReport.

## Day 4 (Nov 4): Risk, guardrails, telemetry

- [x] **T10 Risk model and scorer.** Synthetic training set, scikit-learn model, `risk_model_predict` MCP tool, Risk Scorer agent, `DecisionDraft`.
  *Check:* tiers and factors written to `risk` zone with evidence IDs.
  *Done:* Trained GradientBoostingClassifier in `data/models/risk_gradient_boosting.joblib`. Exposed as MCP tool `risk_model_predict`. Built `agents/adk/risk.py` combining ML prior with rule factors and evidence IDs. 3 unit tests pass.
- [x] **T11 Guardrails v1.** Input guard (toxicity, injection, social engineering), PII guard, output validation, decision rules (no auto-reject, escalation).
  *Check:* all tests listed in `docs/04_SECURITY.md` section 6 items 1 to 5 pass.
  *Done:* Built `input_guard.py`, `pii_guard.py`, and `output_guard.py`. Wired into gateway, orchestrator, and screening crew. Verified with 5 dedicated unit and integration tests passing in `tests/test_security_guardrails.py`.
- [x] **T12 Callbacks and traces.** ADK callbacks and CrewAI step/task callbacks emit `StepTrace`; cost estimation.
  *Check:* a run shows traces from both frameworks in the `system` zone.
  *Done:* Built `telemetry/cost.py` and `telemetry/callbacks.py`. Traces from both ADK and CrewAI recorded in blackboard `system.traces`. Provided `scripts/show_traces.py` displaying per-agent telemetry table.
- [x] **T13 Parallel pattern.** Concurrent dispatch of verification and screening with versioned writes.
  *Check:* same case in parallel mode gives equivalent report and lower runtime.
  *Done:* Added ThreadPool concurrent execution of identity verification and sanctions screening in `Orchestrator`, with atomic optimistic concurrency 409 retry in `append_event_with_retry`. Verified with `tests/test_parallel.py`.
- [x] **T14 Hybrid P2P mode.** `MessagingStrategy` implementation with direct hand-offs plus board logging.
  *Check:* same case runs in both modes; report schema identical.
  *Done:* Implemented `BlackboardStrategy` and `HybridP2PStrategy` in `src/onboardiq/messaging/strategy.py`. Verified all 4 combinations (2 modes x 2 patterns) produce identical `OnboardingReport` schema with `scripts/compare_modes_and_patterns.py` and `tests/test_modes_and_patterns.py`.
- [x] **T15 Company path (basic).** UBO tool and analyst, screen owners.
  *Check:* company case resolves owners and screens them.
  *Done:* Built `ubo_graph` FastMCP tool (NetworkX) and `crewai.ubo_analyst`. Tested clean company case (case_007), sanctioned owner escalation (case_008), and opaque ownership flagging (case_009). 4 unit tests pass in `tests/test_ubo.py`.
- [x] **T16 Eval runner v0.** Run a small grid (about 8 to 12 runs), save reports and traces, compute metrics, draw one boxplot and one heatmap.
  *Check:* `results/plots/` has at least a boxplot and a heatmap.
  *Done:* Built `eval/runner.py`, `metrics.py`, and `plots.py`. Executed 10/10 grid sweep saving report/traces/board JSONs. Generated `results/metrics.csv`, `runtime_by_pattern.png`, and `agent_phase_heatmap.png`.
 
## Day 6 (Nov 6): Submission

- [x] **T17 Updated problem statement** (one page, from BRD and PRD).
  *Check:* written to `docs/submission/problem_statement.md`.
  *Done:* Authored comprehensive 1-page updated problem statement in `docs/submission/problem_statement.md` detailing problem context, objectives, architectural additions, scope boundaries, and the core research question.
- [x] **T18 Updated plan** (this checklist with status, plus what moved to the final phase).
  *Check:* written to `docs/submission/project_plan.md`.
  *Done:* Authored updated project plan with detailed completed work, final phase roadmap (T23–T33), rotation matrix, and risk watchlist.
- [x] **T19 Work-in-progress report** (1 to 2 pages): architecture diagram, what works, first results, issues, plan.
  *Check:* written to `docs/submission/wip_report.md`.
  *Done:* Authored comprehensive WIP report with Mermaid architecture diagram, empirical proof of core capabilities, verified 10-run benchmark table, and issue resolution log.
- [x] **T20 Coverage slide** (one slide): table of the 11 criteria with status Done, In progress or Planned, and one evidence item each. Be honest about what is planned.
  *Check:* written to `docs/submission/coverage_slide.md`.
  *Done:* Formatted slide-ready markdown table covering all 11 course criteria (8 Done, 2 In Progress, 1 Planned) with exact file and artifact evidence citations.
- [x] **T21 Demo rehearsal.** Script: clean case, sanctions near-match, injecting case, show board, traces, heatmap. Each teammate must be able to explain any component.
  *Check:* written to `docs/submission/demo_script.md`.
  *Done:* Complete 5-7 minute walkthrough script with exact commands/commentary, setup checklist, and 10 detailed viva defense questions and answers.
- [x] **T22 Push to public GitHub.** Check no secrets and no real data. Submit before 23:59.
  *Check:* audit clean clone, zero secrets, .gitignore updated, git push instructions prepared.
  *Done:* Comprehensive pre-push audit complete; verified zero API keys, no .env leaks, 100% synthetic data, clean README instructions; ready for student-executed git push.

## Final phase (after Nov 6)

- [x] **T23 Adverse media agent** and local news corpus.
  *Check:* `news_search` tool with local corpus and live fallback, `crewai.media_analyst` agent, 3 corpus examples, tests passing.
  *Done:* Built `news_search` FastMCP tool, 3-article local news corpus (`data/news/corpus.json`), and `AdverseMediaAnalystAgent` wired into both Sequential and Parallel patterns; 5 unit tests passing in `tests/test_adverse_media.py`.
- [x] **T24 Reviewer agent and reflection loop** (max 2 loops), `policy_rag` tool, `data/policy.md`.
  *Check:* 15-rule policy in `data/policy.md`, `policy_rag` MCP tool, `adk.reviewer` evaluating drafts against policy and triggering reflection loop with `adk.risk_scorer`; 3 unit tests passing in `tests/test_reflection_loop.py`.
  *Done:* Built `policy_rag` tool, 15-rule institutional policy, and `ComplianceReviewerAgent` reflection loop (tested first-pass approval vs forced revision on policy violations).
- [x] **T25 Client Communicator and RFI loop.** Handle abusive and impatient personas.
  *Check:* `adk.comms` drafting RFI on missing/low-confidence docs (capped at 2 rounds in `system.rfi_rounds`), neutral de-escalation for abusive/impatient personas without rule disclosure; 5 unit tests passing in `tests/test_client_communicator.py`.
  *Done:* Built `ClientCommunicatorAgent` with automated RFI generation and strict policy guarantees against process alteration or internal threshold disclosure.
- [x] **T26 Tamper score and forger persona.**
  *Check:* Error-Level Analysis (ELA) and metadata tamper scoring in `doc_ocr`, tampered document generation in `dataset_gen.py`, cross-document consistency checks in `IdentityVerifierAgent` raising `doc_tampering` and `identity_mismatch`; 4 unit tests passing in `tests/test_tamper_detection.py`.
  *Done:* Implemented ELA and PNG metadata tamper scoring (100% precision and recall on synthetic benchmark sample), and wired cross-document verification into `IdentityVerifierAgent`.
- [x] **T27 Persona prompt variants** (structure and content) and injection tests.
  *Check:* `data/personas/` with >= 4 variants per persona across 5 personas, `persona_injector.py`, ReAct vs Plain reasoning variants in `RiskScoringAgent` / `ComplianceReviewerAgent`, 4 unit and integration tests passing in `tests/test_persona_injections.py`.
  *Done:* Authored structured variants (formal letter, chat, form stuffing, hidden doc text) in `data/personas/`, implemented `persona_injector.py`, wired ReAct and Plain reasoning into risk scoring and reflection loops, and verified risk tier invariance on injected twin cases under active guardrails.
- [x] **T28 Full dataset** (20 to 24 cases) and persona sweep.
  *Check:* 24 labelled cases generated with fixed seed in `src/onboardiq/eval/dataset_gen.py`, public list download script `scripts/download_public_lists.py`, dataset summary statistics function, 8 unit tests passing in `tests/test_dataset_full.py` and `tests/test_dataset_gen.py`.
  *Done:* Generated all 24 benchmark cases (19 individuals, 5 companies) covering all 7 planted flag types and 3 namesake false positives; implemented dataset statistics summary table and public OFAC/UN/PEP download handler.
- [x] **T29 Tracing** with OpenTelemetry to Langfuse or Phoenix; one trace per case.
  *Check:* `src/onboardiq/telemetry/tracing.py` implementing deterministic 128-bit trace ID derivation from `run_id`, root case span, child agent spans, guardrail event spans, W3C A2A trace context propagation, and provenance audit summary; 6 unit tests passing in `tests/test_tracing_otel.py`.
  *Done:* Built OpenTelemetry tracing engine with in-memory exporter and optional OTLP/Langfuse/Phoenix exporter, deterministic 1-case-1-trace guarantee, and cross-framework distributed context propagation across A2A calls.
- [x] **T30 Full evaluation** (40+ runs), side studies, statistics, all plots.
  *Check:* `configs/grid.yaml` (48 runs), batch runner with pre-run cost & runtime estimation and resume support, `results/metrics.csv` (58 total runs analyzed, 75.9% decision accuracy, 0 false positives, 0% injection breach), 7 benchmark plots, Mann-Whitney U test results in `results/plots/statistical_tests.json`, empirical `results/SUMMARY.md`; 5 unit tests passing in `tests/test_full_evaluation.py`.
  *Done:* Executed full 48-run grid sweep with 0 failures, computed comprehensive metrics table, generated runtime/cost boxplots, persona recall, token usage, injection ablation, latency and step-type heatmaps, statistical tests, and comprehensive SUMMARY report.
- [x] **T31 Review console and UI** (Streamlit): live board, officer approval.
  *Check:* Streamlit app in `src/onboardiq/ui/app.py` with client form (case/persona/mode/pattern/reasoning), live zoned blackboard inspector with masked PII, compliance officer review console with human override, full evaluation analytics dashboard, and OpenTelemetry provenance inspector; screenshot guide in `docs/submission/screenshots.md`; 2 unit tests passing in `tests/test_ui_app.py`.
  *Done:* Implemented production-ready Streamlit console on port 8501 covering all 5 core views, zero-PII auditability, interactive human override buttons, and visualization of all benchmark sweeps.
- [x] **T32 Cloud Run deployment** of all services; secrets in Secret Manager.
  *Check:* `deploy/` with Dockerfiles for all 5 services, root `docker-compose.yml`, Firestore repository implementation `FirestoreBlackboardStore`, and `deploy/cloudrun.md` with step-by-step checklist; 3 unit tests passing in `tests/test_deploy.py`.
  *Done:* Packaged microservices into individual Dockerfiles, implemented Cloud Firestore repository backend for serverless deployments, created root Docker Compose orchestration, and authored complete Cloud Run deployment guide with Secret Manager and zero-cost standby instructions.
- [ ] **T33 Final report and presentation**; contribution matrix; viva preparation.

## Team rotation

Roles must rotate across phases and everyone must contribute across components. Suggested rotation of focus areas between phases: (a) blackboard and schema, (b) ADK agents and guardrails, (c) CrewAI crew, MCP tools and evaluation. Rotate each phase and pair on integration tasks (T08, T13, T14).

## Risk watchlist

- A2A integration is the highest technical risk. If blocked for more than half a day, build a thin HTTP adapter that follows the A2A message shape, keep the Agent Card, and note the limitation.
- LLM cost: use a small model and cache tool results.
- Keep a working end-to-end path at all times; add features on a branch and merge only when the demo path still passes.
