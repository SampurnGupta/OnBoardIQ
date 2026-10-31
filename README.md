# OnboardIQ

Multi-agent KYC/AML client onboarding system with an auditable blackboard.
Course project for CSE3101 Agentic AI (CrewAI + Google ADK only).

## What is in this starter pack

| File | Purpose |
|---|---|
| `AGENTS.md` | Standing rules for the AI coding agent (Antigravity reads this) |
| `docs/01_BRD.md` | Business requirements: why this exists, scope, success measures |
| `docs/02_PRD.md` | Product requirements: functional and non-functional, acceptance criteria, mapped to the 11 course criteria |
| `docs/03_ARCHITECTURE.md` | Architecture and system design: components, data flow, messaging modes, repo layout, deployment |
| `docs/04_SECURITY.md` | Threat model, guardrails, PII handling, persona attack matrix |
| `docs/05_EVALUATION.md` | Dataset spec, experiment grid, metrics, plots |
| `docs/06_IMPLEMENTATION_PLAN.md` | Ordered task checklist with acceptance checks, planned for the Nov 6 deadline |
| `src/onboardiq/schema.py` | Starter Pydantic blackboard schema (the contract every agent shares) |
| `requirements.txt`, `pyproject.toml` | Package list (unpinned; pin after your first working install) and pytest/ruff config |

## How to start in Antigravity

1. Unzip, then open the `onboardiq` folder as a workspace in Antigravity.
2. Make sure `AGENTS.md` is at the workspace root. If your Antigravity version prefers its own rules location (for example `GEMINI.md` or `.agent/rules/`), copy the contents of `AGENTS.md` there. Check the current Antigravity docs for the exact rule file names, since they change between releases.
3. Start the agent in a planning-style mode and give it this first prompt:

   > Read AGENTS.md and everything in docs/. Then do task T01 from docs/06_IMPLEMENTATION_PLAN.md only. Show me the plan first, and stop after T01 so I can review.

4. Work one task at a time. After each task, review the diff, run the acceptance check listed for the task, and tick the box in `docs/06_IMPLEMENTATION_PLAN.md`.
5. Keep secrets in `.env` (never commit it). Create it from the variable names in `docs/03_ARCHITECTURE.md`, section 9.

## Academic integrity reminder

The course handout says AI-generated code and plagiarism are reported under the Unfair Means policy, and every student must be able to explain and modify any part of the project in the demo and viva. Use the agent to plan, scaffold and learn, but read every file it writes, keep functions small, and be ready to rewrite any part yourself. Confirm with your instructor how much AI assistance is acceptable.

## Data safety

Use only synthetic applicants and synthetic documents. Never put real Aadhaar, PAN, passport or other personal data anywhere in this repository.
