# AGENTS.md - rules for the coding agent

You are helping build **OnboardIQ**, a multi-agent KYC/AML client onboarding system for a university course (CSE3101 Agentic AI). Read `docs/` before writing code. If code and docs disagree, stop and ask.

## Hard constraints (never violate)

1. **Agent frameworks:** use only **CrewAI** and **Google ADK**. No LangChain, LangGraph, AutoGen, LlamaIndex agents or other agent frameworks.
2. **Blackboard is mandatory.** All intermediate results are written to and read from the blackboard service as typed Pydantic objects. Agents do not keep private state that other agents need.
3. **Tools via MCP.** Every external capability (OCR, registry lookup, sanctions screening, news search, ML risk model, policy RAG, ownership graph, blackboard access) is exposed by the FastMCP server in `src/onboardiq/mcp_server/` and called through MCP from both frameworks.
4. **Structured output.** Every agent output and the final report must validate against models in `src/onboardiq/schema.py`. Do not change the schema without telling me why.
5. **A2A.** The CrewAI screening crew and the ADK orchestrator communicate over the A2A protocol, each service publishing an Agent Card.
6. **Synthetic data only.** Never use or generate real personal data, and never call real government identity APIs.
7. **No secrets in code or git.** Read keys from environment variables. Keep `.env` in `.gitignore`.
8. **Security by default.** Raw PII stays in the `pii_vault` zone. Outbound tool queries must go through the PII guard. Auto-reject is forbidden; high-risk cases escalate to a human.

## Working agreements

- Work on **one task at a time** from `docs/06_IMPLEMENTATION_PLAN.md`. Show a short plan first, then implement, then stop.
- After each task: run the task's acceptance check, report the result honestly (including failures), and tick the checkbox.
- Prefer small, readable functions and short comments explaining non-obvious logic. The team must be able to explain every file in a viva, so avoid clever or opaque code.
- Write a pytest test for each module that has logic (guardrails, schema validators, metrics, dataset generator).
- When a framework API is uncertain (CrewAI A2A, ADK callbacks, MCP adapters), **check the current official docs** instead of guessing, and note the version you used in `requirements.txt`.
- Do not add new dependencies, services or agents without asking.
- Ask before deleting or renaming files.

## Conventions

- Python 3.11+, type hints everywhere, Pydantic v2.
- Formatting and linting: `ruff`. Tests: `pytest`.
- Each agent has an `agent_id` string (for example `adk.risk_scorer`, `crewai.sanctions_screener`) used in traces, guardrail events and evidence references.
- Every callback emits a `StepTrace`; every guardrail decision emits a `GuardrailEvent`; every conclusion cites `evidence_ids`.
- Run configuration comes from one `RunConfig` (mode, pattern, reasoning, persona, case id) so the evaluation runner can sweep it.

## Definition of done for any task

- Code runs locally with the documented command.
- Acceptance check in the plan passes.
- Tests pass and `ruff` is clean.
- No secrets, no real PII, no unexplained TODOs.
- Plan checkbox ticked and a one-line note added under the task.
