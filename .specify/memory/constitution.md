<!--
Sync Impact Report (temporary review note; remove before committing):
Version change: unratified template -> 1.0.0 (initial adoption).
Added principle: Concise, Precise Documentation.
Added sections: Documentation Scope; Compliance Review; Governance.
Removed: unused template placeholders/examples; no adopted rules removed.
Dependent templates/commands: unchanged; live constitution is the policy source.
Follow-up TODOs: none.
-->

# TradingView MCP Service Constitution

## Core Principles

### Concise, Precise Documentation

- Each `spec.md` MUST target 500 words; `spec.md` and `plan.md` MUST each stay under
  800 words unless essential requirements require more. Any exception MUST include a
  brief justification in the affected document.
- Each requirement MUST have one authoritative location; other documents MUST link
  to it instead of repeating it.
- Each task MUST use one actionable sentence, adding paths and dependencies only
  when necessary. A task line SHOULD stay under 60 words including its paths,
  dependencies and requirement references; move acceptance detail to the contracts.
- `tasks.md` SHOULD stay under 2,500 words. Exceeding that budget requires a brief
  justification in the file, as specs do.
- `tasks.md` MUST hold only task lines and their checkbox state; progress evidence and verification logs belong in `docs/` or a feature status file, and specs state requirements only.
- Documents MUST describe current decisions and omit generic advice,
  conversational history, and redundant summaries; retain history only when needed
  for compatibility or migration.
- Brevity MUST NOT remove security boundaries, failure behavior, testable acceptance
  criteria, or necessary implementation details.
- Revisions MUST preserve existing requirement/task IDs and completion states.

### Infrastructure as Code

- Every AWS resource MUST be defined in a CloudFormation template in the repository and created or changed only by deploying that template. Resources MUST NOT be created by hand in the console or by ad hoc CLI commands.
- Deployments MUST use reviewed template versions and MUST NOT use root account credentials.
- Account-level bootstrap (for example, enabling billing or SSO) is the only exception and MUST be documented.

## Documentation Scope

Apply these rules to future generated or revised specifications, plans, tasks, and
supporting contracts. Keep requirements in specifications, implementation decisions
in plans/contracts, and execution steps in task lists. Add supporting documents or
diagrams only when they clarify necessary detail without repeating existing content.

## Compliance Review

Before finishing an artifact, check its word budget, remove repetition, and confirm
that requirements, task states, and essential security/failure details remain intact.
This adoption does not automatically rewrite existing feature documents.

## Governance

These rules govern Spec Kit documentation in this project. Amendments MUST record
the changed rule, rationale, version, and amendment date. Use a major version for
incompatible rule changes, a minor version for new or expanded principles, and a
patch version for clarifications. Reviews MUST check compliance with this constitution.

## Amendment Record

- **1.2.0 — 2026-11-13**: Added Infrastructure as Code: AWS resources only from CloudFormation templates, no root credentials, documented bootstrap exceptions. Rationale: the service publishing role and ECR repository must be reproducible and reviewable.
- **1.1.0 — 2026-11-10**: Added soft length budgets for task lines (under 60 words) and `tasks.md` (under 2,500 words), with justification required to exceed them. Rationale: the service task list had grown to paragraphs of acceptance detail, obscuring task status.
- **1.0.1 — 2026-11-10**: Clarified that `tasks.md` holds only task lines and checkbox state, with progress evidence in `docs/` or a status file. Rationale: task files had accumulated dated evidence logs, which made counts and status drift out of sync.

**Version**: 1.2.0 | **Ratified**: 2026-11-04 | **Last Amended**: 2026-11-13
