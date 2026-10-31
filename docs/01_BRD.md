# 01 - Business Requirements Document (BRD)

## 1. Background

Banks and fintechs must verify every new client (KYC) and screen them for money-laundering and sanctions risk (AML) before opening an account. Today this is slow, manual and inconsistent: analysts re-key document data, run searches across several systems, and write justifications by hand. Delays lose customers, and inconsistent or poorly documented decisions create regulatory exposure.

## 2. Business problem

- Onboarding takes days because document checks, screening and risk assessment are done sequentially by people.
- Fuzzy name matches against sanctions lists produce many false positives that waste analyst time.
- Decisions are hard to audit: it is often unclear which evidence supported which conclusion.
- Sensitive personal data spreads across tools and is exposed to more systems than necessary.
- Clients can try to pressure staff, submit forged documents or hide instructions in documents to manipulate automated systems.

## 3. Proposed solution

**OnboardIQ**: a team of specialised AI agents that extracts document data, verifies identity, screens sanctions and politically exposed persons (PEP), checks adverse media, resolves company beneficial owners, scores risk, and drafts a decision, with a compliance reviewer agent challenging the result and a human officer approving anything high-risk. Every step is recorded on a shared, typed blackboard with evidence references.

## 4. Business objectives

| ID | Objective | Measure |
|---|---|---|
| BO1 | Reduce onboarding turnaround | Parallel pattern run time vs sequential pattern run time per case |
| BO2 | Improve consistency and accuracy of decisions | Decision accuracy and risk-tier agreement against labelled synthetic cases |
| BO3 | Catch more genuine red flags | Red-flag recall and precision against planted flags |
| BO4 | Reduce wasted analyst effort | False-positive rate on namesake and clean cases |
| BO5 | Make every decision auditable | 100 percent of decisions carry resolvable evidence references |
| BO6 | Protect personal data | Zero PII leaks to outbound tools across all evaluation runs |
| BO7 | Resist manipulation | Injection and social-engineering success rate near zero with guardrails on |
| BO8 | Keep cost predictable | Mean and spread of cost per case reported per configuration |

## 5. Stakeholders

| Stakeholder | Interest |
|---|---|
| Compliance officer (human) | Reviews escalated cases, needs clear evidence and rationale |
| Onboarding analyst | Wants fewer false positives and less manual data entry |
| Client | Wants a fast, polite, clear process and clear requests for missing documents |
| Regulator / auditor | Needs traceable decisions and data-protection compliance |
| Course instructors | Need all 11 minimum criteria met, demonstrable and measurable |
| Project team | Needs a buildable scope within the course timeline |

## 6. Scope

**In scope:** individual and company onboarding; document extraction; identity verification against a mock registry; sanctions and PEP screening using public lists; adverse media check; beneficial owner resolution; ML plus rule-based risk scoring; compliance review; human escalation console; evaluation harness; cloud deployment.

**Out of scope:** real government API integration, real customer data, ongoing transaction monitoring, account opening itself, production-grade legal compliance certification, mobile apps.

## 7. Assumptions and constraints

- All data is synthetic. Sanctions list names are public; applicants are synthetic or perturbed.
- Only CrewAI and Google ADK may be used as agent frameworks.
- Blackboard shared state, MCP tools, A2A, Pydantic outputs, callbacks, observability, 40 or more evaluation runs and cloud deployment are mandatory course criteria.
- Team of 2 to 3 students, roles rotate across phases, every member must explain any component.
- Delivery milestone: Project 2 evaluation on Nov 6, final phase in the last week of the course.
- LLM and cloud costs must stay within student budgets; use a small, cheap model for the 40-run sweeps.

## 8. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| CrewAI or ADK A2A APIs differ from docs or change | Blocks interoperability | Spike A2A early (task T07); keep a thin adapter layer |
| LLM cost or rate limits during 40 runs | Evaluation incomplete | Cheap model, caching of tool results, run in batches |
| Scope too large for the deadline | Missing demo | Build the minimum viable demo first (see plan), add agents later |
| Flaky LLM outputs break the pipeline | Failed runs | Pydantic validation with retries, low temperature, deterministic tools |
| Real data accidentally used | Policy and ethics issue | Synthetic generator only, PII guard, review before commit |

## 9. Success criteria

The project is successful when: all 11 minimum criteria are demonstrably met; a live demo onboards at least one individual and one company end to end; the evaluation reports at least 40 runs with boxplots, heatmaps and a labelled dataset; and every team member can explain any component.
