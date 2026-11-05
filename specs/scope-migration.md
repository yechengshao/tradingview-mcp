# Scope Migration — 2026-11-03

## Project separation — 2026-11-04

Specs 002 (authentication/API access) and 003 (billing/subscriptions) moved into the separate sibling project [mcp-auth-subscriptions](../../mcp-auth-subscriptions/README.md). This repository retains service-only spec 001 and its active feature selection. Cross-project documentation links are updated; existing task IDs/check states, reviewer checklists, runtime code, infrastructure, workflows, dependencies and historical evidence are preserved. The sections below record the earlier in-repository planning split, not the current project layout. No deployment or billing action is part of this move.

The user requested service-only spec 001, a separate Stripe billing Lambda/DynamoDB, and subscription enforcement in the custom authorizer. The earlier combined infrastructure expansion is redistributed into separate features in this repository. This is a documentation/task-ownership change, not implementation or cloud migration.

## Preserved work

Original service T001–T044 keep their IDs, descriptions and checkbox states: 42 checked; T040/T044 live acceptance unchecked. Its existing report schema and both checklist files are byte-identical. Source/templates/workflows/locks and prior 516-test evidence are unchanged; no new access/billing readiness is inferred. The active feature selector remains 001.

## Historical split mapping (before REST revision)

Former spec-001 T045–T061 were all unchecked and are replaced at the time of the split by the following ownership. New IDs are feature-local; no completed task was transferred or renamed.

| Former 001 ID | Active destination |
|---|---|
| T045 combined contracts | 001:T047 service interface; 002:T001 access ownership |
| T046 authorizer tests | 002:T002 |
| T047 authorizer handler | 002:T003, including confirmed entitlement enforcement |
| T048 authorizer image | 002:T004 |
| T049 auth template | 002:T005 |
| T050 import preparer | 002:T006 |
| T051 gateway template | 002:T007 |
| T052 publishing-IAM tests | 001:T045 |
| T053 publishing-IAM stack | 001:T046 |
| T054 combined artifact workflow | 002:T008 separate authorizer workflow; service workflow remains service-only |
| T055 combined verifier tests | 001:T047 and 002:T009 |
| T056 combined verifier | 001:T048 and 002:T009 |
| T057 combined docs | 001:T049 and 002:T010 |
| T058 combined CI | 001:T050 and 002:T011 |
| T059 combined local acceptance | 001:T050 and 002:T012 |
| T060 combined audit | 001:T050 and 002:T012 |
| T061 combined live acceptance | Preserved 001:T040/T044, 002:T013 and spec 003's separately planned payment acceptance |

Subsequent pending access descriptions were revised for the REST/OAuth journey; this table is historical, so former HTTP import tasks no longer imply that an import helper will be built. The authoritative active lists are [service tasks](001-add-lambda-deployment/tasks.md) and [access tasks](../../mcp-auth-subscriptions/specs/002-authentication-api-access/tasks.md). Billing is a new [draft spec](../../mcp-auth-subscriptions/specs/003-billing-subscriptions/spec.md), not an executable task list or implemented Lambda/table. It needs its own technical plan and tasks before implementation.

## Contract ownership

- Access authorization, gateway migration and identity release contracts move to 002; old 001 links are forwarding documents.
- Service runtime/ECR/publication/publishing-IAM stay in 001. Delivered legacy HTTP attachments remain service-owned; the new REST target assigns every gateway attachment/invoke permission to 002, with a service-only runtime supplying its alias.
- Billing customer/subscription/event/entitlement data and provider ingress belong to 003. The access authorizer gets minimal read-only entitlement access; the service gets none.
- Confirmed human PKCE and authorizer subscription enforcement are preserved. Initial active-paid/no-grace billing assumptions are documented as assumptions, not invented user answers.
- Provider secrets, identity scopes, prices and billing-state transitions do not enter the service native provider map or application role.

Future cross-feature acceptance reuses a matching running target and captures observations before cleanup; one feature's local report never establishes another feature's live acceptance. Imported API/identities/shared providers and billing data are retained under their owning feature's policy.

Validation: original task lines/states and service checklists/schema/selector are preserved; all feature links/IDs/task coverage and shell/JSON examples pass document checks. This split changes documentation only.


## Subsequent REST and paid OAuth revision — 2026-11-03

The user described Cognito login → plan selection/order → Stripe payment → AI-client login completion, then explicitly chose REST API with native usage plans. This supersedes prior HTTP adoption/no endpoint change planning. No HTTP API is converted in place: create a separate REST API/named stage, validate it, explicitly change client resource/endpoints and secure/disable any legacy endpoint as part of scoped cutover. No deletion/provisioning was performed.

Spec 002 adds OAuth coordination/state/signing, one-use code+PKCE completion after verified persisted billing entitlement and native subscriber-binding readiness, short-lived plan/expiry-bound bearer tokens with revalidated rotating refresh, and top-level usageIdentifierKey (no injected x-api-key). Native per-subscriber keys map to tier plans; native quotas remain best effort. Spec 003 adds requested plan-selection/order/Checkout/activation/expired-continuation recovery contracts; billing still needs a physical technical plan/tasks. Separate service authentication/billing-free scope is preserved.

Task preservation: original 001 T001–T050 lines/states stay unchanged; five new unchecked REST-only tasks T051–T055 make 55 total, 42 checked/13 pending. Access T001–T013 IDs remain unchecked with revised pending descriptions, plus T014–T021, all 21 pending. This replaces obsolete pending HTTP import/profile work rather than marking it complete. The v1 service report schema, two 001 checklist files and active feature selector stay byte-identical. A new REST report-v2 schema is a future task, not a claimed file/working verifier.

The new authoritative interfaces are [client onboarding](../../mcp-auth-subscriptions/specs/002-authentication-api-access/contracts/client-onboarding.md), [REST gateway](../../mcp-auth-subscriptions/specs/002-authentication-api-access/contracts/rest-gateway.md), [service handoff](001-add-lambda-deployment/contracts/rest-migration.md), [billing onboarding](../../mcp-auth-subscriptions/specs/003-billing-subscriptions/contracts/checkout-onboarding.md) and [entitlements](../../mcp-auth-subscriptions/specs/003-billing-subscriptions/contracts/entitlements.md). Source, templates, workflows, locks, image artifacts and historical 516-test results are untouched by this documentation revision. Validate document traceability/links/preserved markers separately; AWS/Stripe/host acceptance remains not_run under local-only instruction.

## Step Functions onboarding revision — 2026-11-03

The user selected Step Functions for multiple authentication/payment callbacks and payment-result waiting. Spec 002 now owns a Standard state machine with private callback waits, short access handlers, bounded billing reconciliation/Wait retries and strict original authorization deadline. Cognito verification, billing writes, OAuth code/token exchange and synchronous REQUEST authorizer responsibilities remain with their existing owners. No Lambda or HTTP request waits through human/payment delay; no Express callback workflow is planned.

The new [workflow contract](../../mcp-auth-subscriptions/specs/002-authentication-api-access/contracts/onboarding-workflow.md) defines durable commit-before-signal, register-then-recheck, early/duplicate/reordered/late event handling, task-token/history privacy, stop/timeout/redrive recovery and immutable worker execution targets. Spec 003 adds durable activation outbox/stream and short reconciliation operation requirements, without depending on a workflow ARN or receiving task tokens. Billing after expired OAuth remains paid and is reused on fresh sign-in.

Existing 001 task lines/checklist/schema/selector stay unchanged. Access T001–T021 stay unchecked; pending descriptions/dependencies are reconciled and T022–T025 add explicit workflow work: 25 tasks, zero complete. Billing now has 20 requirements/9 success criteria and still needs its technical plan/tasks; access has 21 requirements/10 success criteria. No runtime/IaC code, source lock, image, cloud deployment or payment action is changed by this planning update. Local-only validation remains in force.


<details>
<summary>Historical service planning and validation records</summary>

## Historical Service Planning Validation Record

The 2026-11-01 reconciliation supersedes the former service bearer gate, public Function URL, token-digest configuration/rotation, and 120/150-second deadline assumptions. Compatible image/publishing/SDK lifecycle and release-evidence decisions are retained. Validation passed: Draft 2020-12 report schema; two accepted synthetic report shapes and 13 rejected invalid shapes; all 13 local Markdown links; syntax checks for six shell blocks without execution; and a cross-artifact design review. The spec and its quality checklist were preserved. No before_plan/after_plan extension hooks are configured. Synthetic schema checks are design validation only, never deployment evidence. No application changes, image builds, AWS mutations, or live deployment tests are performed by this planning workflow.

Native-environment planning update: all nine `.env.example` keys map directly to Lambda environment configuration. The current scope uses masked provider-credential deployment inputs and no configuration-fetching startup hook, application SDK addition, or provider-storage IAM. Environment update/rollback follows published Lambda value snapshots. Validation passed for all nine key mappings, 22 local documentation links, six shell blocks (syntax only), and the JSON deployment-input example. All 52 reviewer item IDs/checkbox states were preserved. The spec, built-in checklist, and report schema remain unchanged; no application code, image build, or AWS resource was modified by this planning change.

Analysis remediation on 2026-11-02 defines the immutable pre-feature baseline, the completed-interaction/cold-start correlation predicate, and the separate optional-dependency CI job with lazy verifier AWS imports. Task IDs and reviewer checklist states remain unchanged. Validation passed for 44 task IDs/labels/markers and their backward-only dependencies, all FR/SC assignments, 28 local links, seven shell blocks (syntax only), and the preserved structural report schema; validation is planning-only.


## Service-Only Split — 2026-11-03

Spec 001 owns MCP runtime/service provision, ECR, service image publication and publishing IAM. Spec 002 owns identity/gateway/authorizer/adoption and subscription access enforcement; spec 003 owns Stripe processing in a separate Lambda and DynamoDB. The active feature selector remains 001. Existing service schema/checklists/source and original completed task states are preserved. [Scope migration](#contract-ownership) records redistribution of pending combined work. Earlier 516-test evidence is service-runtime evidence only. Current validation is documentation-only; billing/access implementation and cloud acceptance are not claimed.


## Scope-Split Validation — 2026-11-03

Validated service spec IDs (17 FR/8 SC), access spec IDs (12 FR/5 SC) and billing draft IDs (14 FR/6 SC). Active service tasks are 50 total/42 checked; access tasks are 13 total/zero checked; billing has no generated implementation task list. Every active service/access requirement and outcome is assigned. New local task dependencies point to earlier IDs. Original service T001–T044 task lines/states, both service checklist files, report schema and active feature selector are byte-identical to the pre-split snapshot.

All 92 local Markdown references, 15 shell blocks (syntax only) and 4 JSON examples validated. New built-in specification-quality reviews record writing quality separately from implementation or business-policy approval. Billing's prices, physical storage/secret delivery and reviewable eligibility assumptions remain its own planning inputs. No runtime tests were rerun because source/templates/workflows/dependencies were not changed; earlier 516 service tests are not evidence of new access/payment behavior. No AWS/Stripe operation or specification extension hook ran; no hooks are configured.

</details>
