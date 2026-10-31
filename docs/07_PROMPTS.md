# 07 - Antigravity Prompt Playbook

Use these prompts in order, one per session or task. T01 is the prompt you already have:

> Read AGENTS.md and everything in docs/. Then do task T01 from docs/06_IMPLEMENTATION_PLAN.md only. Show me the plan first, and stop after T01 so I can review.

## How to use

1. Paste one prompt at a time. Let the agent show its plan, approve it, then let it implement.
2. When it stops, run the acceptance check yourself, read the diff, and ask about anything you do not understand.
3. Tick the task in `docs/06_IMPLEMENTATION_PLAN.md`, commit, then move to the next prompt.
4. If a session gets long or confused, start a new one with the **Reset prompt** below.

## Helper prompts

**Reset prompt (new session, any time)**
> Read AGENTS.md and everything in docs/. Look at the checkboxes in docs/06_IMPLEMENTATION_PLAN.md and the current repo state, then tell me in 5 lines what is done, what is half-done, and what the next unchecked task is. Do not write code yet.

**Failing check prompt**
> The acceptance check for task <Txx> is failing. Here is the output: <paste>. Find the root cause first and explain it in plain words. Then propose the smallest fix, wait for my approval, and apply it. Do not refactor anything unrelated.

**Framework-docs prompt (use before any CrewAI, ADK, A2A or MCP work)**
> Before coding, check the current official documentation for <CrewAI / Google ADK / A2A / MCP> for the exact class names and install steps for what we need. Tell me the versions you will use and any difference from what the docs/ files assume. Then continue.

**Viva prep prompt (after each task, important for academic integrity)**
> Explain the code you just wrote for task <Txx> as if teaching a student who must defend it in a viva. Walk through each file, why each design choice was made, what could break, and give me 5 likely viva questions with short answers. Then ask me 3 questions to check I understand.

**Commit prompt**
> Show me `git status` and a summary of changes for task <Txx>. Check there are no secrets, no .env, and no real personal data. Suggest a commit message. Do not commit until I confirm.

---

## Day 1: Foundations

### T02 Schema
> Do task T02 only. Review src/onboardiq/schema.py against docs/03_ARCHITECTURE.md and docs/02_PRD.md. List any gaps or inconsistencies before changing anything. Then add tests in tests/test_schema.py for: DecisionDraft validators, PiiVault defaults, a full Blackboard round trip through model_dump_json and model_validate_json, RunConfig defaults, and LabelledCase validation. Do not rename or remove fields without asking me. Run pytest and ruff and report the real output. Stop after T02.

### T03 Blackboard service
> Do task T03 only. First show the plan. Then build the Blackboard Service from docs/03_ARCHITECTURE.md section 7: a FastAPI app in src/onboardiq/blackboard/service.py, a SQLite repository in store.py behind a small repository interface (so Firestore can be added later), and a client library in client.py. Requirements: zones as in the schema; access table by agent_id exactly as in section 3 of the architecture doc; append-only event log; every write carries expected_version and returns 409 on mismatch; 403 on forbidden zone with a guardrail_event of category access_denied written to the system zone. Add tests for read/write, 403, 409, and event log ordering. Show me how to run the service locally. Stop after T03.

### T04 Synthetic data generator
> Do task T04 only. Build src/onboardiq/eval/dataset_gen.py with a fixed seed. Generate 10 synthetic labelled cases following docs/05_EVALUATION.md section 1: 6 individuals and 4 companies, covering clean, namesake false positive, identity mismatch, sanctions near-match, and one opaque-ownership company. Use Faker for applicants, PIL to render simple synthetic ID and address-proof images, and create a mock registry SQLite DB at data/registry.db with valid synthetic IDs for the clean cases. For sanctions, create a small placeholder list file data/lists/sanctions_sample.csv with obviously fake names plus a README telling me where to download the public OFAC and UN lists later. Every case JSON must validate as LabelledCase. Never use real personal data. Add a test that all generated cases validate. Stop after T04.

## Day 2: Tools and first ADK agents

### T05 MCP tool server
> Do task T05 only. Run the framework-docs prompt for FastMCP first. Then build src/onboardiq/mcp_server/server.py with one file per tool under tools/: registry_lookup (SQLite), sanctions_screen (RapidFuzz over the list file, returning scored candidates), doc_ocr (pytesseract or PDF text, returns text, extracted fields and a tamper_score placeholder of 0.0 for now), blackboard_read and blackboard_write (calling the Blackboard client with the caller agent_id). All tool inputs and outputs must be Pydantic models. Add a small script scripts/mcp_smoke_test.py that lists the tools and calls each one on a generated case. Add unit tests for sanctions_screen scoring. Stop after T05.

### T06 ADK extractor and gateway (basic)
> Do task T06 only. Run the framework-docs prompt for Google ADK first. Build the ADK Security Gateway (src/onboardiq/agents/adk/gateway.py) and Document Extraction Agent (extractor.py). The gateway takes an application, splits raw PII into the pii_vault zone, writes a MaskedProfile to the intake zone, and logs a GuardrailEvent with category clean (real checks come in T11). The extractor connects to the MCP server via ADK's MCP toolset, calls doc_ocr, and writes DocumentRecord and ExtractedField items with EvidenceRef to the board. Agents must output schema-valid objects only. Provide a script scripts/run_t06.py that runs both on one generated case and prints the board zones. Stop after T06.

## Day 3: CrewAI crew and A2A

### T07 CrewAI screening crew
> Do task T07 only. Run the framework-docs prompt for CrewAI and its MCP adapter first. Build src/onboardiq/agents/crewai/screening_crew.py with two agents for now: Identity Verifier and Sanctions/PEP Screener. They use MCP tools (registry_lookup, sanctions_screen, blackboard_read/write) and write IdentityCheck and ScreeningHit records with evidence references. The Sanctions Screener must classify each candidate as true_match, likely_match, false_positive or unresolved with reasoning, and must read only the masked profile. Use Task guardrails to validate output against the schema. Provide scripts/run_t07.py that runs the crew standalone on one case. Stop after T07.

### T08 A2A link
> Do task T08 only. This is the highest-risk task. First run the framework-docs prompt for A2A (the a2a-sdk, ADK's remote agent support, and CrewAI's A2A support if any). Show me the plan and any API differences before coding. Then wrap the CrewAI screening crew in an A2A server (src/onboardiq/agents/crewai/a2a_server.py) with an Agent Card describing its skills, and have the ADK side call it through a remote A2A client. Keep the adapter thin. Log every A2A call as a StepTrace with step_type a2a. Provide scripts/run_t08.py that starts the A2A server and triggers it from an ADK agent, and show the Agent Card JSON. If true A2A cannot be made to work within reasonable effort, tell me exactly why and propose a thin HTTP adapter that follows the A2A message shape instead. Stop after T08.

### T09 Orchestrator (sequential, blackboard mode)
> Do task T09 only. Build the ADK Orchestrator in src/onboardiq/agents/adk/orchestrator.py as a hierarchical coordinator. For now implement Sequential pattern and Blackboard mode only. Phases: intake, extraction, screening (via A2A to the CrewAI crew), then a placeholder risk step that sets a rule-based tier from flags (the ML scorer comes in T10), then decision. Apply the decision rules from docs/03_ARCHITECTURE.md section 6: LOW with no flags approves; MEDIUM approves with enhanced monitoring or requests info; HIGH or true/likely sanctions or PEP escalates; never auto-reject. Assemble and validate an OnboardingReport. Provide scripts/run_case.py taking --case and printing the report as JSON. Run on a clean case and on a sanctions near-match case and show both results. Stop after T09.

## Day 4: Risk, guardrails, telemetry

### T10 Risk model and scorer
> Do task T10 only. Generate a separate synthetic risk-training dataset (a few hundred rows, features: country risk, occupation risk, monthly volume, number of red flags, max screening score, tamper score, client type) from rules plus noise, with a fixed seed. Train a scikit-learn gradient boosting classifier, save it to data/models/, and expose risk_model_predict as an MCP tool. Build the Risk Scoring Agent (agents/adk/risk.py) that combines the ML probability with rule-based factors into RiskAssessment (0 to 100, tier, factors with evidence_ids) and writes a DecisionDraft. Replace the placeholder risk step in the orchestrator. Add tests for tier thresholds and for factor evidence ids. Stop after T10.

### T11 Guardrails v1
> Do task T11 only. Follow docs/04_SECURITY.md exactly. Implement src/onboardiq/guardrails/: input_guard.py (toxicity using a local classifier or a simple lexicon fallback, injection patterns, social-engineering patterns), pii_guard.py (blocks outbound tool arguments containing ID numbers, DOB or full address from the pii_vault), and output_guard.py (Pydantic validation, decision rules, no PII in text). Wire them into ADK callbacks (before_model, before_tool, after_tool, after_model) and into CrewAI tool wrappers and task guardrails. Every decision creates a GuardrailEvent on the board. Add a guardrails_enabled flag in RunConfig that turns them off for ablation. Implement the security tests 1 to 5 listed in section 6 of the security doc and run them. Stop after T11.

### T12 Callbacks and traces
> Do task T12 only. Implement src/onboardiq/telemetry/callbacks.py and cost.py. ADK callbacks and CrewAI step_callback, task_callback or event listeners must create StepTrace records (agent_id, phase, step_type, name, latency, tokens, cost, error) and write them to the system zone. Add a cost estimator driven by a small price table in config. Provide scripts/show_traces.py that prints a per-agent summary table for a run. Run one full case and show traces from both frameworks. Stop after T12.

## Day 5: Patterns, modes, first evaluation

### T13 Parallel pattern
> Do task T13 only. Add the Parallel pattern to the orchestrator: after extraction, dispatch identity verification, sanctions screening and (when available) media and UBO concurrently, then join before risk. Use versioned writes with retry on 409. Keep the Sequential pattern working and selectable by RunConfig.pattern. Run the same case in both patterns, show that the reports are equivalent in content, and show the runtime difference. Add a test for concurrent writes to the same zone. Stop after T13.

### T14 Hybrid P2P mode
> Do task T14 only. Implement a MessagingStrategy interface in src/onboardiq/messaging/strategy.py with two implementations: BlackboardStrategy (hand-offs only via the board) and HybridP2PStrategy (upstream results also passed directly to the next agent, while the board still stores state and the audit log). Select it from RunConfig.mode. Both modes must produce identical report schemas. Run one case in all four combinations of mode and pattern and show a comparison table of runtime, tokens and result. Stop after T14.

### T15 Company path (basic)
> Do task T15 only. Add the UBO path: a ubo_graph MCP tool (NetworkX) that takes an ownership chart and returns owners above 10 percent with paths, and a UBO Analyst in the CrewAI crew that writes UBOEntry records and sends each owner through sanctions screening. Raise an opaque_ownership red flag when the chain cannot be resolved. Run a clean company case, an opaque-ownership case and a company with a sanctioned owner, and show the results. Stop after T15.

### T16 Eval runner v0
> Do task T16 only. Build src/onboardiq/eval/runner.py, metrics.py and plots.py following docs/05_EVALUATION.md. The runner takes a YAML grid, runs each configuration catching exceptions, and saves report.json, traces.json and a board snapshot under results/{run_id}/. metrics.py computes the metrics table to results/metrics.csv. plots.py produces at least one boxplot (runtime by pattern) and one heatmap (agent x phase latency). Run a small grid of 8 to 12 runs, tell me honestly how many succeeded, and show the output file list. Stop after T16.

## Day 6: Submission (Nov 6)

### T17 Updated problem statement
> Do task T17 only. Write docs/submission/problem_statement.md, one page, using docs/01_BRD.md and docs/02_PRD.md. Include the problem, objectives, what changed since the first submission (ask me what the earlier statement said if you need it), scope, and the research question about messaging modes and patterns. Plain language, no invented results.

### T18 Updated plan
> Do task T18 only. Write docs/submission/project_plan.md from docs/06_IMPLEMENTATION_PLAN.md and the actual checkbox status in the repo: what is done, what is in progress, what moves to the final phase, a revised timeline to the last week of the course, and a team responsibility matrix with roles rotating across phases. Do not claim anything that is not working.

### T19 Work-in-progress report
> Do task T19 only. Write docs/submission/wip_report.md (1 to 2 pages): architecture overview, what works now with evidence (commands run and outputs), first evaluation results with the real numbers from results/, issues found, and next steps. Include an architecture diagram in text or Mermaid form. Report failures honestly.

### T20 Coverage slide
> Do task T20 only. Produce the content for the single coverage slide as docs/submission/coverage_slide.md: a table of the 11 minimum criteria with columns Status (Done, In progress, Planned), Evidence (a file, command or screenshot), and Next step. Base statuses on what is actually in the repo and passing. Keep it to what fits on one slide. I will build the slide myself from this table.

### T21 Demo rehearsal
> Do task T21 only. Write docs/submission/demo_script.md: a 5 to 7 minute demo with exact commands and what to say: clean case, sanctions near-match, injecting case, then the board, traces, heatmap and boxplot. Add a section of 10 likely questions per team member area with short answers, and a checklist for pre-demo setup (services up, keys loaded, data generated, fallback screenshots).

### T22 Push to GitHub
> Do task T22 only. Audit the repository before pushing: search for secrets, .env files, API keys, real-looking personal data, large generated files, and anything that should be in .gitignore. Verify README instructions work from a clean clone by listing the exact commands. Fix .gitignore if needed and give me the git commands to create and push a public repo. Do not push anything yourself.

## Final phase

### T23 Adverse media agent
> Do task T23 only. Add news_search as an MCP tool with two backends: a local news corpus in data/news/ (default, reproducible) and an optional live search API chosen by env var. Add the Adverse Media Analyst to the CrewAI crew. It must use only the masked profile, judge whether an article is about this specific person (relevance 0 to 1), paraphrase rather than copy article text, and write MediaFinding records plus an adverse_media red flag when relevant. Wire it into both patterns. Build 3 corpus examples: relevant, namesake, and none. Add tests and show results.

### T24 Reviewer agent and reflection loop
> Do task T24 only. Write a short KYC policy in data/policy.md (about 15 numbered rules) and build a policy_rag MCP tool over it. Build the Compliance Reviewer ADK agent: it checks the DecisionDraft against policy, writes PolicyCheck and Challenge items, and if challenges are unresolved the Risk Scorer revises the draft. Maximum 2 loops. Record revision counts. Show one case where the reviewer forces a revision and one where it passes first time.

### T25 Client Communicator and RFI loop
> Do task T25 only. Build the Client Communicator ADK agent. When documents are missing or fields have low confidence it drafts a polite request for information (max 2 rounds, tracked in system.rfi_rounds). For impatient or abusive messages it replies politely and neutrally, never reveals internal rules, thresholds or case details, and never changes the process. Add tests with sample abusive and impatient messages and show outputs.

### T26 Tamper score and forger persona
> Do task T26 only. Improve doc_ocr tamper detection (simple error-level analysis or metadata and font inconsistency checks on the synthetic images) and extend dataset_gen.py to produce tampered documents with known labels. Add cross-document consistency checks to the Identity Verifier. Raise doc_tampering and identity_mismatch red flags. Report precision and recall of tamper detection on the generated set.

### T27 Persona prompt variants and injection tests
> Do task T27 only. Create data/personas/ with at least 4 prompt variants per persona (cooperative, impatient, abusive, forger, injecting), varying both structure (for example formal letter, chat message, form field stuffing, hidden text in a document) and content. Add a persona injector that applies a persona to a base case. Also add ReAct vs plain prompt variants for the negotiating-style reasoning in agents via RunConfig.reasoning. Add an integration test that the injecting persona does not change the risk tier compared with its clean twin case, with guardrails on.

### T28 Full dataset and persona sweep
> Do task T28 only. Expand dataset_gen.py to the full 20 to 24 labelled cases with the composition in docs/05_EVALUATION.md, download-and-load instructions for the real public OFAC and UN lists (I will download them myself), and a PEP list built from public sources. Regenerate everything with the fixed seed. Add dataset statistics output (counts by group and flag type). Show the stats.

### T29 Tracing with OpenTelemetry and Langfuse
> Do task T29 only. Run the framework-docs prompt first for OpenTelemetry instrumentation of CrewAI and Google ADK and for Langfuse or Phoenix export. Implement src/onboardiq/telemetry/tracing.py so one case equals one trace, using run_id as the trace id and propagating it across A2A calls. Include tool calls and guardrail events as spans. Make exporting optional through env vars. Show me what to look at in the dashboard to prove provenance.

### T30 Full evaluation
> Do task T30 only. Create configs/grid.yaml for the full grid in docs/05_EVALUATION.md (2 modes x 2 patterns x 5 personas x 2 cases = 40 runs minimum) plus the reasoning side study and the guardrail ablation. Estimate the total cost and time first and wait for my approval. Then run in batches with resume support, randomised order and recorded seeds. Generate metrics.csv, all boxplots, the three heatmaps, the injection ablation bar chart, and Mann-Whitney or bootstrap comparisons for mode and pattern. Write results/SUMMARY.md with the real numbers and one-line takeaways, including how many runs failed and why. Do not invent or smooth any numbers.

### T31 Review console and UI
> Do task T31 only. Build a Streamlit app in src/onboardiq/ui/app.py with: a client form (choose case and persona, upload documents), a live blackboard view showing zones with PII masked, an officer console for escalated cases (see evidence, rationale, approve or reject, which writes human_override to the review zone), and a results page that loads results/ and shows the plots. Never display raw PII. Provide the run command and take a short list of screenshots I should capture for the report.

### T32 Cloud Run deployment
> Do task T32 only. Run the framework-docs prompt for Cloud Run deployment of Python services. Create deploy/ with a Dockerfile per service (blackboard-svc, mcp-tools, screening-crewai, orchestrator-adk, ui), a Firestore repository implementation for the blackboard store selected by env var, and deploy/cloudrun.md with exact gcloud commands, Secret Manager usage, service-to-service token handling, and cost-control tips such as min instances 0. Do not deploy anything yourself and do not ask me to paste any keys into chat. Give me a step-by-step checklist I run myself.

### T33 Final report and presentation
> Do task T33 only. Using the real results in results/ and the repo, draft the final report in the course template (ask me for the template headings if you do not have them): problem, architecture, implementation, security, evaluation with figures and statistics, limitations, and conclusions. Draft a slide outline for the final presentation with one key message per slide, a demo flow, and a contribution matrix template for the group and self assessment. Mark any claim that still needs evidence.

---

## Final-week checklist prompt

> Check every item against the repo, not from memory. For each of the 11 minimum criteria in docs/02_PRD.md, show the file and the command that demonstrates it and whether it passes right now. List anything missing, and anything claimed in docs/ that the code does not do. Do not fix anything yet; give me the list.
