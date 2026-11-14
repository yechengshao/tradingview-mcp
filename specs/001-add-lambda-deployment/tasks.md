---
description: "Dependency-ordered implementation tasks for Add AWS Lambda Deployment"
---

# Tasks: Add AWS Lambda Deployment

**Status and history**: [status.md](status.md). Task IDs and checkbox states are authoritative here: 47 of 58 checked. Original T001–T044 keep their completion states; T045–T055 and T058 are service follow-up; access and billing work is tracked in [spec 002](../../../mcp-auth-subscriptions/specs/002-authentication-api-access/tasks.md) and [spec 003](../../../mcp-auth-subscriptions/specs/003-billing-subscriptions/tasks.md).

**Inputs**: [spec](spec.md), [plan](plan.md), [research](research.md), [data model](data-model.md), [contracts](contracts/deployment.md), [quickstart](quickstart.md).
**Format**: `- [ ] T### [P] [US#] Task. Files: paths. Depends: IDs. Covers: requirements.` `[P]` marks independent files, not permission to edit shared files concurrently.
**Rule**: A task is checked only when its own acceptance ran. Missing cloud, account or evidence prerequisites stay `not_run`; never check off an unperformed live step or infer success from mocks. Reviewer-owned checklist markers are not changed by these tasks.

## Phase 1: Setup

- [X] T001 Add the optional Python 3.11 deployment tooling group and record baseline_ref in the baseline manifest, leaving production dependencies unchanged. Files: `pyproject.toml`, `uv.lock`, `tests/integration/support/baseline.json`. Covers: FR-006, FR-012.
- [X] T002 [P] Create the Lambda build-context allowlist that excludes environment files, credentials, tests and evidence without changing the original Docker build context. Files: `Dockerfile.lambda.dockerignore`. Covers: FR-005–FR-007.

## Phase 2: Foundation

- [X] T003 [P] Build separate-process baseline and Lambda MCP launch helpers with controlled provider fixtures, deriving expectations only from the frozen baseline. Files: `tests/integration/support/provider_fixture.py`, `tests/integration/support/baseline.json`. Depends: T001, T002. Covers: FR-003, FR-004, FR-011, FR-012.
- [X] T004 [P] Add contract tests for the verification report schema that reject fabricated complete reports. Files: `tests/unit/test_verification_report.py`, `specs/001-add-lambda-deployment/contracts/verification-report.schema.json`. Depends: T001, T002. Covers: FR-011, FR-013, SC-007.
- [X] T005 [P] Add structural CloudFormation tests for ECR immutability, scanning, encryption, ownership, scoped pull access and retention. Files: `tests/integration/test_deployment_contract.py`. Depends: T001, T002. Covers: FR-007, FR-015.
- [X] T006 Implement the project-owned ECR bootstrap stack with immutable tags, scanning, encryption, scoped pull access, ownership tags and retention. Files: `infra/lambda/ecr.yaml`. Depends: T005. Covers: FR-007, FR-009, FR-015.
- [X] T007 Create the verifier report and CLI foundation for local, live and combine modes, with all 16 stages initialized to `not_run`. Files: `scripts/verify_lambda.py`. Depends: T004. Covers: FR-013, FR-014, SC-007.

## Phase 3: User Story 1 — Tool access through Lambda (P1, MVP)

- [X] T008 [P] [US1] Write Lambda-only unit tests for import isolation, Host/Origin rules, slash and method handling, the nine native settings and redacted failures. Files: `tests/unit/test_lambda_server.py`. Depends: T003, T006, T007. Covers: FR-002, FR-004, FR-005, FR-008, FR-010.
- [X] T009 [P] [US1] Write wire-level parity tests for initialization, paginated discovery of all 39 tools, controlled results and concurrent requests against the frozen baseline. Files: `tests/integration/test_lambda_transport.py`. Depends: T003, T006, T007. Covers: FR-003, FR-004, FR-011, SC-002, SC-003.
- [X] T010 [P] [US1] Extend infrastructure tests for digest-only ARM64 deployment, NoEcho inputs, the log-only role, retained versions and alias, and the absence of Function URLs or public principals. Files: `tests/integration/test_deployment_contract.py`. Depends: T003, T006, T007. Covers: FR-001, FR-005, FR-009, FR-015.
- [X] T011 [P] [US1] Write image-driven tests for the ARM64 image: non-root access, read-only root, packaged coinlists, readiness, one finite MCP interaction and credential exclusion. Files: `tests/integration/test_lambda_container.py`. Depends: T003, T006, T007. Covers: FR-001, FR-004, FR-008, FR-010, FR-011.
- [X] T012 [US1] Implement the Lambda entrypoint that validates native configuration, imports the server once in stateless JSON mode and makes no configuration-fetching call. Files: `src/tradingview_mcp/lambda_server.py`. Depends: T008, T009. Covers: FR-001, FR-002, FR-004, FR-006.
- [X] T013 [US1] Add Lambda-only loopback and execute-api Host validation, Origin rejection, `/mcp/` normalization, 405 handling and an unauthenticated `GET /health` with no upstream calls; no bearer or JWT authentication is implemented. Files: `src/tradingview_mcp/lambda_server.py`. Depends: T012. Covers: FR-002, FR-004, FR-005, FR-008, FR-010, FR-014.
- [X] T014 [US1] Implement the locked Python 3.11-slim ARM64 image with the Lambda Web Adapter, pinned upstream digests and labels for source commit, lock digest and release tag. Files: `Dockerfile.lambda`. Depends: T013, T011, T002. Covers: FR-001, FR-003, FR-007, FR-008, FR-010.
- [X] T015 [US1] Implement the runtime stack with log group, scoped log role, ARM64 function, sizing, ownership tags and explicit failure on incompatible inputs, with no VPC or application AWS permission. Files: `infra/lambda/runtime.yaml`. Depends: T010, T006, T014. Covers: FR-001, FR-005, FR-009, FR-010, FR-014, FR-015.
- [X] T016 [US1] Map the nine application settings directly to native Lambda environment variables through NoEcho parameters, with no retrieval hook, runtime SDK or provider-read permission. Files: `infra/lambda/runtime.yaml`, `src/tradingview_mcp/lambda_server.py`. Depends: T015, T008. Covers: FR-005, FR-009, FR-010, FR-014.
- [X] T017 [US1] Create a revision-bound published version and stable `live` alias, retaining replaced versions. Files: `infra/lambda/runtime.yaml`. Depends: T016. Covers: FR-001, FR-004, FR-009.
- [X] T018 [US1] Attach an AWS_PROXY payload-2.0 integration to the supplied HTTP API for `ANY /mcp`, `ANY /mcp/` and `GET /health`, all CUSTOM with the supplied authorizer, scoped to the alias. Files: `infra/lambda/runtime.yaml`. Depends: T017. Covers: FR-002, FR-005, FR-009, FR-015, SC-004.
- [X] T019 [US1] Run the US1 unit, transport, container and infrastructure checks and record them in the report, leaving authorization `not_run`. Files: `scripts/verify_lambda.py`. Depends: T018, T009, T011, T007. Covers: FR-001–FR-004, FR-011, FR-013.

## Phase 4: User Story 2 — Existing deployment options keep working (P1)

- [X] T020 [P] [US2] Add Docker and stdio regression tests for documented commands, ports, health and tool interaction, using baseline expectations. Files: `tests/integration/test_original_transports.py`. Depends: T003, T007, T006. Covers: FR-006, FR-012, SC-006.
- [X] T021 [P] [US2] Add compatibility tests for the original image publishing workflow against the frozen baseline. Files: `tests/integration/test_release_workflow_contract.py`, `.github/workflows/publish-image.yml`. Depends: T003, T007, T006. Covers: FR-007, FR-012, SC-006.
- [X] T022 [US2] Integrate the original launch checks into verifier local mode, managing only run-owned processes and containers. Files: `scripts/verify_lambda.py`. Depends: T020, T019. Covers: FR-006, FR-012, SC-006.
- [X] T023 [US2] Run the existing hermetic unit suite and release-workflow assertions, fixing only Lambda-owned regressions. Files: `scripts/verify_lambda.py`, `tests/unit/test_tool_annotations.py`, `tests/unit/test_tool_offload.py`. Depends: T022, T021. Covers: FR-003, FR-006, FR-007, FR-012, SC-006.

## Phase 5: User Story 3 — Deploy, update and roll back from documentation (P2)

- [X] T024 [P] [US3] Add rendered-template tests for rollback selection, forward clearing of `RollbackVersion`, environment-only publication, outputs, scoped deletion and preserved supplied resources. Files: `tests/integration/test_deployment_contract.py`. Depends: T018, T023. Covers: FR-009, FR-014, FR-015, SC-001.
- [X] T025 [P] [US3] Add publication tests for manual-only dispatch, OIDC trust, scoped ECR push, immutable tags and binding the tested config digest to the pushed manifest. Files: `tests/integration/test_lambda_publication.py`. Depends: T014, T021. Covers: FR-007, FR-009, FR-015.
- [X] T026 [US3] Complete retained-version selection, outputs and deletion ownership so each publication has a fresh revision and rollback changes no client authorization. Files: `infra/lambda/runtime.yaml`. Depends: T024, T017. Covers: FR-009, FR-015, SC-001.
- [X] T027 [P] [US3] Add the manual ECR publication workflow that builds once, runs native gates and pushes the same image without deploying. Files: `.github/workflows/publish-lambda-image.yml`. Depends: T025, T019, T023. Covers: FR-007, FR-009, SC-006.
- [X] T028 [US3] Write the clean-checkout deploy, update, rollback and cleanup guide, including preflight, OIDC setup and manual MCP smoke steps. Files: `docs/lambda-deployment.md`. Depends: T026, T027. Covers: FR-002, FR-005, FR-007–FR-010, FR-014, FR-015.
- [X] T029 [US3] Document the nine-setting matrix, private parameter-file handling, NoEcho limits, configuration-only update and rollback, and external Cognito credential separation, using placeholders only. Files: `docs/lambda-deployment.md`. Depends: T028, T016. Covers: FR-005, FR-009, FR-010, FR-014, FR-015, SC-001, SC-004.
- [X] T030 [US3] Define the lifecycle evidence procedure with a sanitized example, clearly distinct from an executed walkthrough. Files: `docs/lambda-deployment.md`, `specs/001-add-lambda-deployment/contracts/verification-report.schema.json`. Depends: T029. Covers: FR-009, FR-015, SC-001.

## Phase 6: User Story 4 — Health and deployment readiness (P2)

- [X] T031 [P] [US4] Add verifier semantic tests for provenance, exit codes, stage completeness, full-success gates, cold-start joins and redaction, including health-only starts that must not count. Files: `tests/unit/test_verify_lambda.py`. Depends: T007, T003. Covers: FR-011, FR-013, FR-014, SC-007.
- [X] T032 [P] [US4] Add mocked AWS and HTTP tests for read-only control-plane use, exact route bindings and denial-before-backend correlation, and a Python 3.11 deployment-test CI job that fails rather than skips. Files: `tests/integration/test_lambda_verifier.py`, `.github/workflows/test-lambda.yml`. Depends: T007, T003. Covers: FR-005, FR-008, FR-011, FR-013, FR-014, SC-004.
- [X] T033 [US4] Complete verifier local mode for invalid input, upstream error parity, provider-independent health and ten warm health checks under five seconds. Files: `scripts/verify_lambda.py`. Depends: T031, T023, T019. Covers: FR-008, FR-010–FR-013, SC-005.
- [X] T034 [US4] Implement read-only live target resolution that binds alias, digest, labels, native settings and the gateway route shape without dumping environments. Files: `scripts/verify_lambda.py`. Depends: T032, T033, T018. Covers: FR-005, FR-011, FR-013, FR-014, SC-004.
- [X] T035 [US4] Implement live credential-denial checks for every feature route, requiring 401/403 with gateway correlation proving no service invocation. Files: `scripts/verify_lambda.py`. Depends: T034. Covers: FR-005, FR-011, FR-013, FR-014, SC-004.
- [X] T036 [US4] Implement live protocol checks: at least 20 complete interactions, five simultaneous clients, ten health probes, invalid input, and `completed-interactions.json` with request correlations. Files: `scripts/verify_lambda.py`. Depends: T035. Covers: FR-002, FR-004, FR-008, FR-010, FR-011, SC-003, SC-005.
- [X] T037 [US4] Implement scoped CloudWatch and Lambda evidence for at least two fresh environments whose startup joins a completed interaction, without forcing cold starts. Files: `scripts/verify_lambda.py`. Depends: T036. Covers: FR-004, FR-011, FR-013, SC-003.
- [X] T038 [US4] Implement combine validation beyond the schema: image and config identity, count and threshold checks, lifecycle subset rules and revalidation of every counted cold record. Files: `scripts/verify_lambda.py`. Depends: T037, T031. Covers: FR-011–FR-013, SC-001, SC-003, SC-007.
- [X] T039 [US4] Finalize argument validation, sanitized reports and exit codes: 0 full success, 1 failed, 2 incomplete, 3 invalid input. Files: `scripts/verify_lambda.py`. Depends: T038. Covers: FR-013, FR-014, SC-007.
- [ ] T040 [US4] Run the verifier and test acceptance matrix against the tested release, recording explicit `not_run` for unavailable live stages. Files: `scripts/verify_lambda.py`, `/tmp/tradingview-lambda-evidence/local.json`, `/tmp/tradingview-lambda-evidence/live.json`. Depends: T039, T029. Covers: FR-011–FR-014, SC-003–SC-005, SC-007.

## Phase 7: Polish and completion

- [X] T041 [P] Add the Lambda deployment entry to the README, keeping the original Docker instructions. Files: `README.md`. Depends: T040, T030. Covers: FR-006, FR-007, FR-009.
- [X] T042 [P] Reconcile the quickstart with delivered paths, the input schema, verifier stages and exit codes. Files: `specs/001-add-lambda-deployment/quickstart.md`. Depends: T040, T030. Covers: FR-009, FR-010, FR-013, FR-014.
- [X] T043 Audit artifacts for credential leakage, public invocation paths, unsupported streaming, ownership and Docker/GHCR drift. Files: `infra/lambda/runtime.yaml`, `Dockerfile.lambda`, `.github/workflows/publish-lambda-image.yml`, `docs/lambda-deployment.md`. Depends: T041, T042. Covers: FR-003, FR-005–FR-007, FR-010, FR-014, FR-015.
- [ ] T044 Execute the clean-checkout deploy, distinct-image update, rollback and environment-only walkthrough, clean up owned resources, then combine evidence. Files: `scripts/verify_lambda.py`, `docs/lambda-deployment.md`, `/tmp/tradingview-lambda-evidence/lifecycle.json`, `/tmp/tradingview-lambda-evidence/final.json`. Depends: T043, T040, T030. Covers: FR-009, FR-011–FR-013, FR-015, SC-001, SC-007.

## Phase 8: Service publishing and sibling-interface follow-up

- [X] T045 [P] Add service publishing-IAM tests for exact repository and environment trust, selected ECR actions, and no deployment, identity or billing permissions or static keys. Files: `tests/integration/test_publishing_iam.py`. Depends: T025, T043. Covers: FR-007, FR-015, FR-016.
- [X] T046 Implement `publishing-iam.yaml` with nonsecret role and provider outputs; reused account providers are never duplicated, mutated or deleted implicitly. Files: `infra/lambda/publishing-iam.yaml`. Depends: T045, T006. Covers: FR-007, FR-015, FR-016.
- [ ] T047 [P] Add boundary tests proving no identity, Stripe or DynamoDB runtime dependency or grant, and that bypass integrations are rejected by exact function identity, not name prefix. Files: `tests/integration/test_deployment_contract.py`, `tests/integration/test_lambda_verifier.py`, `tests/unit/test_lambda_server.py`. Depends: T039, T043. Covers: FR-005, FR-006, FR-011, FR-012, FR-015, FR-017, SC-008.
- [ ] T048 Reconcile service preflight and read-only verification with optional spec-002 gateway outputs, keeping the v1 16-stage report and missing-live `not_run` behavior. Files: `scripts/verify_lambda.py`. Depends: T047, T046. Covers: FR-005, FR-011, FR-013, FR-014, FR-016, FR-017, SC-007, SC-008.
- [ ] T049 Reconcile the service docs, quickstart and README with the publishing IAM bootstrap and spec-002 interface outputs, keeping the GHCR workflow unchanged. Files: `docs/lambda-deployment.md`, `specs/001-add-lambda-deployment/quickstart.md`, `README.md`. Depends: T048, T046. Covers: FR-007, FR-009, FR-010, FR-015–FR-017, SC-001, SC-008.
- [ ] T050 Run affected service checks and audit that no Stripe, DynamoDB or identity permission or package enters MCP; sibling fixtures are not live acceptance. Files: `tests/unit/`, `tests/integration/`, `.github/workflows/test-lambda.yml`, `.github/workflows/publish-lambda-image.yml`, `specs/001-add-lambda-deployment/tasks.md`. Depends: T049, T048. Covers: FR-005–FR-007, FR-012–FR-017, SC-006–SC-008.

## Phase 9: REST service transport and evidence

- [X] T051 Add packaged pinned-adapter REST-v1 event tests for stage and path handling, headers, query, base64 bodies, exact host and finite MCP behavior, keeping current HTTP tests. Files: `tests/integration/test_lambda_rest_transport.py`. Depends: T019, T043. Covers: FR-002–FR-006, FR-008, FR-010, FR-012, FR-017, SC-002, SC-005, SC-006, SC-008.
- [x] T052 Test, then implement `runtime-rest.yaml` with the function, log role, native environment, live alias and the outputs spec 002 needs; it creates no gateway method, integration or permission. Files: `infra/lambda/runtime-rest.yaml`, `tests/integration/test_deployment_contract.py`, `src/tradingview_mcp/lambda_server.py` only if T051 requires it. Depends: T051. Covers: FR-001, FR-002, FR-004, FR-005, FR-008, FR-010, FR-015, FR-017, SC-001, SC-005, SC-008.
- [ ] T053 Test, then add the explicit REST report-v2 schema and profile selection, rejecting cross-profile reports while keeping v1 unchanged. Files: `specs/001-add-lambda-deployment/contracts/verification-report-v2.schema.json`, `scripts/verify_lambda.py`, `tests/unit/test_verification_report.py`, `tests/integration/test_lambda_verifier.py`. Depends: T048, T052. Covers: FR-005, FR-011, FR-013–FR-015, FR-017, SC-003, SC-004, SC-007, SC-008.
- [ ] T054 Update service docs, local CI and REST examples for the service-only stack, gateway-owned attachments, distinct old and new endpoints, and scoped cutover and rollback. Files: `docs/lambda-deployment.md`, `specs/001-add-lambda-deployment/quickstart.md`, `.github/workflows/test-lambda.yml`, `tests/integration/`. Depends: T049, T050, T051, T052, T053. Covers: FR-006, FR-007, FR-009, FR-010, FR-012–FR-015, FR-017, SC-001, SC-006–SC-008.
- [ ] T055 Only with explicit live prerequisites, run REST public-transport, denial, no-bypass, release, cold-concurrency and rollback acceptance against the spec-002 gateway, keeping the legacy endpoint secured. Files: `docs/lambda-deployment.md`, `/tmp/tradingview-lambda-evidence/rest-live.json`. Depends: T054 and a deployed protected REST target. Covers: FR-002, FR-005, FR-009, FR-011, FR-013–FR-015, FR-017, SC-001, SC-003, SC-004, SC-007, SC-008.

## Phase 10: MCP observability

- [X] T056 Add isolated CloudWatch JSON, redaction and context tests, plus conditional tracing IAM and template tests. Covers: FR-014, FR-018, SC-009.
- [X] T057 Implement stdlib-only Lambda diagnostics and native AWS tracing settings, IAM and operator guidance, preserving ordinary transports. Depends: T056. Covers: FR-006, FR-014, FR-017, FR-018, SC-006, SC-008, SC-009.
- [ ] T058 Validate the native ARM64 image and, with separate authorization, live CloudWatch and X-Ray delivery and sampling overhead. Depends: T057. Covers: FR-011, FR-013, FR-018, SC-007, SC-009.

## Dependencies

Setup and foundation gate every story. US1 is the MVP; US2 and US3 depend on it; US4 verifier work integrates US1 and US2 output. Polish (T041–T044) follows US4. Service follow-up (T045–T050) and REST work (T051–T055) follow the completed local verifier. Shared-file edits to `infra/lambda/runtime.yaml`, `scripts/verify_lambda.py` and `lambda_server.py` must run in task-ID order.
