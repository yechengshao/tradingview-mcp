# Status and History: Add AWS Lambda Deployment

This file holds dated progress, validation evidence and scope history moved out of [tasks.md](tasks.md). Task IDs and checkbox states live only in tasks.md.

## Scope split

This task list is service-only. Original T001–T044 retain their exact completion states. Pending access/gateway work moved to [spec 002](../../../mcp-auth-subscriptions/specs/002-authentication-api-access/tasks.md); separate billing Lambda/DynamoDB and entitlement ownership are specified in [spec 003](../../../mcp-auth-subscriptions/specs/003-billing-subscriptions/spec.md). See [the migration map](../scope-migration.md). ECR/publishing IAM and service-interface work remain here; no task adds identity/billing logic to MCP.

## Completion and validation history

**Generation validation**: 44 unchecked tasks; phase counts 2/5/12/4/7/10/4; story counts US1 12, US2 4, US3 7, US4 10; 18 parallel markers. IDs, phase/story labels, exact paths, earlier-ID dependency references, local document links, all FR/SC references, and verbatim data-model table constraint coverage were checked. The final walkthrough gathers live evidence before cleanup. No pre/post tasks extension hooks are configured. This validates task structure and traceability, not implementation or deployment success.
**Analysis remediation — 2026-11-02**: C1 adds completed-interaction/cold-start request correlation and rejection cases; U1 pins the pre-feature baseline and immutable expectations; U2 specifies lazy verifier imports and a separate optional-group deployment-test CI job. Existing task IDs, dependency references, and checkbox states are retained. Validation passed for 44 task IDs/labels/markers, their backward-only dependencies, all FR/SC assignments, 28 links, seven shell blocks (syntax only), and the preserved structural report schema. No implementation or live verification is claimed.

## Historical Service Implementation Status — 2026-11-02

42 of 44 tasks are implemented and checked. The user explicitly authorized proceeding past the checklist gate; custom reviewer markers remain unchanged (63 unchecked), and the built-in requirements checklist remains 16/16 checked. No requirements-quality approval is inferred.

Validation: 516 hermetic unit/integration tests passed with both native ARM64 images (no skipped tests), including frozen-baseline catalog/controlled error parity, concurrency/replacement, read-only image storage, limits, original Docker/stdio behavior, gateway snapshots, private configuration intent, and semantic evidence/combine cases. Both CloudFormation templates pass cfn-lint; documentation links, JSON examples, and shell/workflow blocks validate. Existing production metadata/dependencies and original locked versions are preserved. No AWS resource has been changed and no ECR image published. The local build explicitly records dirty source.

Local verifier evidence: `/private/tmp/tradingview-lambda-evidence/local.json` — all 10 locally eligible stages pass; six cloud/lifecycle stages remain not_run, exit 2, full_deployment_success false. `/private/tmp/tradingview-lambda-evidence/live.json` is explicitly an unperformed report with unknown target/release fields left null, not live evidence. Validation summary: `/private/tmp/tradingview-lambda-evidence/implementation-validation.json`; full test record: `/private/tmp/tradingview-lambda-evidence/final-local-pytest.xml`.

T040 remains unchecked for real supplied-target acceptance (authorization-before-backend, 20 interactions/five clients/two correlated fresh environments, and live release identity). T044 remains unchecked for the clean-checkout AWS deploy/distinct-image update/rollback, same-image configuration lifecycle, scoped cleanup and final combined acceptance. Supply the region, disposable stack name, existing compatible HTTP API/REQUEST authorizer, published release and external credential/correlation prerequisites before those steps. No final lifecycle/combine success has been fabricated. No implementation extension hooks are configured.


## Phase 8 status

**Current service status**: 50 tasks; 42 checked; 8 pending (T040, T044, T045–T050). Earlier 516-test/local evidence remains service-runtime evidence. No source/template/workflow/dependency or AWS change is made by this documentation split. The active feature selector remains spec 001; checklists and report schema are preserved. Subscription enforcement and billing readiness are accepted separately by specs 002/003.

## Phase 9 revision

**Revision — 2026-11-03**: User-confirmed REST native usage plans supersede the earlier future HTTP-only profile. Original T001–T050 lines/states remain historical/existing service work. T047–T050 apply to legacy behavior/interface checks; the new REST profile is explicitly additive below. No existing v1 report is reinterpreted as REST proof. Access owns all REST attachments/permissions; billing/OAuth remain outside the service. No reviewer marker is changed.

## Phase 10 status

**AWS-native observability implementation — 2026-11-08:** T056/T057 use stdlib diagnostics and native Lambda/API Gateway tracing only; no OpenTelemetry, tracing SDK, exporter, collector or custom span remains. 114 affected tests pass (one original-image Docker case explicitly deselected), plus 479 unit tests in a separate overlapping run; CloudFormation lint and package builds pass; native ARM64/cloud delivery remains T058. Original dependency and launch boundaries are preserved.
Current total: **58 tasks, 44 checked, 14 unchecked**. Existing REST/publishing/live tasks and reviewer markers retain their states; no cloud deployment, image publication or notification ran.

## T051 local increment (2026-11-11)

`tests/integration/test_lambda_rest_transport.py` with hand-written REST-v1 fixtures in `tests/integration/fixtures/rest_v1/` covers canonical POST/GET routing, trailing slash, base64 bodies, repeated headers and query, the exact host and Origin rules, 405 with Allow POST, stateless JSON responses, and rejection of HTTP API payload 2.0 events; 12 pass. The event-to-HTTP step is a test model of the adapter's documented mapping, because the pinned Lambda Web Adapter 1.1.0 image could not be pulled here (public ECR rate limit, and the GitHub release download returned no binary). T051 stays unchecked until the packaged adapter is exercised through a simulated Runtime API against the built image. Stage-prefixed event paths are not routed, so base-path stripping stays unimplemented as the contract requires.

## T052 local increment (2026-11-11)

`infra/lambda/runtime-rest.yaml` is the REST-profile service stack: function, log group, log-only role, published version and `live` alias, with no API Gateway resources or invocation permissions. It takes `RestApiId` for the execute-api host and exposes the nine identity and alias outputs that access needs. `tests/integration/test_deployment_contract.py` asserts those invariants, and it passes with the existing contract tests (7). `cfn-lint` passes on the template. Live deployment, and the packaged-adapter checks that T051 still needs, are not run, so T052 stays unchecked.

## Publication workflow test gate (2026-11-11)

`publish-lambda-image.yml` now runs `tests/integration/test_lambda_container.py` against the exact built image (`lambda-tested:local`) before the local verifier gate and before any ECR login or push, with `REQUIRE_LAMBDA_CONTAINER_TESTS=1` so missing Docker or image prerequisites fail rather than skip. `test-lambda.yml` also runs the REST-v1 transport checks. Neither workflow has run yet; the first run on GitHub's ARM runner is the real evidence. The packaged-adapter Runtime API checks (T051) are not yet in the workflow.

## Push-triggered Docker tests (2026-11-11)

`.github/workflows/test-docker.yml` builds the image on the ARM runner for every push and pull request to `main` and runs `test_lambda_container.py` against it, with prerequisites required rather than skipped. It does not push to ECR. The Lambda Web Adapter (T051) layer is not yet covered; those checks still need a Runtime Interface Emulator step. Not yet run on GitHub.

## Docker test quota (2026-11-11)

`test-docker.yml` now runs only when image inputs change (Dockerfile, dependency lock, source, container tests), plus manual dispatch. Concurrent runs on the same ref cancel older ones. Reason: ARM runner minutes are limited, and it was running on every push. `test-lambda.yml` (hermetic checks on `ubuntu-latest`) is unchanged.

## Service publishing IAM (2026-11-11)

`infra/lambda/publishing-iam.yaml` (T045 tests first, T046 template) creates the GitHub OIDC provider (retained, since none exists in the account), and a publisher role trusted only for `yechengshao/tradingview-mcp` in the `lambda-publication` environment. Its only permissions are ECR login and pushing/reading images in the `tradingview-mcp-lambda` repository. `tests/integration/test_publishing_iam.py` passes (4 tests) and `cfn-lint` passes. Not deployed. The GitHub thumbprints in the provider are copied from GitHub's published values and must be verified before deployment. T045/T046 stay unchecked until a deploy and a real publish run confirm them.

## Publishing trust fix: immutable subject claims (2026-11-13)

The repository uses immutable OIDC subject claims, so GitHub's `sub` is `repo:yechengshao@7886247/tradingview-mcp@1423980237:environment:lambda-publication`, not the name-based form. `publishing-iam.yaml` now takes `GithubSubjectPrefix` with that value, and the test asserts it. The stack must be updated to apply the corrected trust policy; the retained OIDC provider is unchanged.

## T045–T046 accepted (2026-11-13)

Publishing IAM is checked: the `tradingview-mcp-publishing` stack deployed in account 503098479806, region ca-central-1, with the immutable subject claim. The "Publish Lambda image to ECR" run succeeded and pushed `tradingview-mcp-lambda:run-43365692167-1` (digest `sha256:78599d01e49636c17ac82bbb7f27eb651225ca45bc4c2e944d2ce7c2a72d4c35`). Caveats: the stack was created and updated with root credentials; the GitHub thumbprints are not yet verified against GitHub's current documentation; T040 and T044 remain open until a real deploy and the adapter test (T051) pass.
