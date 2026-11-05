# Research: AWS Lambda Deployment

**Profile revision — 2026-11-03**: The user selected REST API with native usage plans. The [REST service handoff](contracts/rest-migration.md) governs the new target and supersedes any HTTP-only exclusion below for future work. Existing HTTP API v2/`$default`/payload2.0 routes, commands and report-v1 details below describe the delivered **legacy HTTP profile**, not an implemented REST deployment. New service-only runtime/report-v2 work is pending; spec 002 owns all new REST attachments and invoke permissions.

**Date**: 2026-11-01 (reconciled with accepted clarifications). Research is design evidence, not a record of successful builds or deployment tests. Repository observations and official versioned sources are used below. All design questions are resolved.

## 1. Preserve tool registration and the existing launch paths

**Decision**: Add `tradingview_mcp.lambda_server` and reuse the existing `server.mcp` registration in one process. Keep `server.main`, Docker/Compose, and GHCR publication behavior unchanged.

**Rationale**: Repository inspection found 39 decorated tools and one shared FastMCP object. Reusing it avoids schema and annotation drift. The lock resolves MCP 1.29.0, Starlette 0.47.2, Uvicorn 0.35.0, and HTTPX 0.28.1. No framework or SDK migration is needed.

**Alternatives considered**: Duplicating tools or moving every registration into a new server factory increases regression scope. Globally changing transport settings would alter current Docker behavior.

**Sources**: `src/tradingview_mcp/server.py`, `pyproject.toml`, `uv.lock`; [FastMCP 1.29.0 source](https://github.com/modelcontextprotocol/python-sdk/blob/v1.29.0/src/mcp/server/fastmcp/server.py).

## 2. Stateless JSON requires lifecycle and method controls

**Decision**: Configure `stateless_http=True` and `json_response=True` before app creation; preserve the SDK application's lifespan, use one Uvicorn worker, and reject GET/DELETE `/mcp` with 405. Internally normalize `/mcp/` without redirects.

**Rationale**: The SDK creates a fresh stateless transport for each request, but JSON mode does not remove its GET SSE path. Returning buffered JSON avoids long-lived streams and cross-instance session dependencies. SDK lifespan runs the session manager; an outer wrapper must pass it through.

**Alternatives considered**: Stateful SSE, session affinity, or distributed session storage introduce unnecessary dependencies. Blind mounting without lifespan breaks session-manager initialization; slash redirects may advertise an HTTP URL behind the adapter.

**Sources**: [SDK server guide](https://github.com/modelcontextprotocol/python-sdk/blob/v1.29.0/docs/server.md), [HTTP transport](https://github.com/modelcontextprotocol/python-sdk/blob/v1.29.0/src/mcp/server/streamable_http.py), [session manager](https://github.com/modelcontextprotocol/python-sdk/blob/v1.29.0/src/mcp/server/streamable_http_manager.py).

## 3. Preserve exact gateway authority behind the adapter

**Decision**: Keep SDK DNS-rebinding protection enabled with exact loopback/readiness authorities and the supplied API's execute-api hostname (with optional `:443`). Reject Origin headers for this nonbrowser profile and ignore forwarded-host values. No downstream Host rewrite or Function URL hostname pattern is required.

**Rationale**: Adapter 1.1.0 retains the incoming Host header when forwarding to the local process. ApiId/region determine the public hostname before function creation, removing the former generated-URL dependency concern. HTTP API payload 2.0 combines duplicate headers, so former raw-edge duplicate Authorization/Host guarantees cannot be carried over. Restrict the initial profile to an existing auto-deploy `$default` stage and default execute-api endpoint: there is no named-stage/base-path normalization dependency.

**Alternatives considered**: Disabling SDK protection globally would affect existing deployments. Named stages/custom-domain mappings expand path/authority coverage and remain outside this initial integration profile. A Function URL and application credential gate conflict with the clarified boundary.

**Sources**: [SDK transport security](https://github.com/modelcontextprotocol/python-sdk/blob/v1.29.0/src/mcp/server/transport_security.py), [adapter 1.1.0 forwarding](https://github.com/awslabs/aws-lambda-web-adapter/blob/v1.1.0/src/lib.rs), [HTTP API payload format](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html).

## 4. Use a pinned adapter and strict readiness

**Decision**: Use Lambda Web Adapter 1.1.0, port 8000, `/health`, healthy status exactly 200, and buffered invocation. Resolve/pin upstream image digests when implementing the Dockerfile and record them as build evidence.

**Rationale**: AWS's adapter supports the existing HTTP process and non-AWS Python base image. Its documented default readiness range accepts 100–499; explicitly accepting only 200 prevents a missing route or failed authorization from being treated as readiness. Existing `/health` returns `{"status":"ok"}` without querying providers.

**Alternatives considered**: Writing a custom Lambda Runtime API client is unnecessary. Merely exposing port 8000 cannot satisfy Lambda invocation requirements.

**Sources**: [Adapter README/configuration](https://github.com/aws/aws-lambda-web-adapter), [1.1.0 release](https://github.com/aws/aws-lambda-web-adapter/releases/tag/v1.1.0), `server.py` health route.

## 5. Package a separate locked ARM64 runtime

**Decision**: Use matching Python 3.11-slim stages, uv 0.13.1, `uv sync --locked --no-dev --no-editable`, and a narrowly allowlisted build context. Build a single ARM64 image with attestation attachments disabled; validate read-only root plus writable `/tmp`.

**Rationale**: Lambda accepts one architecture and same-region ECR images. The original image installs from project constraints without using the lock; the new image can improve dependency repeatability without changing that existing release path. Coinlist reads are packaged-file reads and current caches are in-memory. Locked pytest 9.0.3 and pytest-asyncio 1.4.0 support Python 3.10+, so Python 3.11 test execution is compatible.

**Alternatives considered**: Changing the original Dockerfile would expand scope. Reusing a multi-architecture manifest is incompatible. A full-repository COPY risks including local agent configuration and credentials. Native ARM CI is preferred; QEMU remains a build fallback, not a native performance benchmark.

**Sources**: [Lambda image requirements](https://docs.aws.amazon.com/lambda/latest/dg/images-create.html), [uv Docker guide](https://docs.astral.sh/uv/guides/integration/docker/), [uv 0.13.1](https://github.com/astral-sh/uv/releases/tag/0.13.1), [GitHub runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners), [Docker multi-platform strategies](https://docs.docker.com/build/building/multi-platform/).

## 6. Spec 002 supplies access; spec 003 supplies billing

**Decision**: Attach to a separately supplied same-account/same-region HTTP API v2, REQUEST custom authorizer, and auto-deploy `$default` stage. Create only the feature's AWS_PROXY payload-2.0 integration and protected `ANY /mcp`, `ANY /mcp/`, `GET /health` routes. The service implements no MCP client authentication or client-token/digest storage. Upstream provider credentials are separately injected through the environment mapping in decision 11. Clients obtain/refresh a credential through the supplied Cognito flow and send the header expected by the custom authorizer.

**Rationale**: The feature split assigns authentication/gateway provisioning and subscription enforcement to spec 002, and billing state/Stripe processing to spec 003. This service feature consumes their interface without provisioning or querying those components. CUSTOM route authorization runs before backend invocation; denial responses belong to the gateway/authorizer. Local readiness can stay credential-free because it is not a public entrypoint. HTTP API's integration supports the existing adapter through direct Lambda invocation; a Function URL is unnecessary.

**Alternatives considered**: An application bearer/JWT verifier, generated shared token, service OAuth endpoints, Cognito provisioning, and a new gateway/authorizer all conflict with the clarified scope. Using HTTP proxy integration to a public Function URL would leave an avoidable bypass path.

**Integration prerequisites**: The owner supplies Cognito policy/client instructions, AuthorizerId and its API Gateway invocation permission, header identity configuration, authorization-cache behavior compatible with all feature routes, and sanitized access-log evidence. Existing exact or method-specific `/mcp`, `/mcp/`, and `/health` conflicts are rejected rather than overwritten. The API owner reserves these paths; route definitions affect all stages, while backend permission permits only the selected `$default` stage. No shared stage deployment is mutated by this feature.

**Sources**: [HTTP API Lambda authorizers](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-lambda-authorizer.html), [route configuration](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-apigatewayv2-route.html), [route selection](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-routes.html), [stage deployment](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-stages.html).

## 7. Scoped CloudFormation attachment and effective limits

**Decision**: Preserve two stacks: ECR bootstrap, then runtime. Runtime owns logs, execution role, function, retained versions, live alias, feature integration/routes, and alias-scoped `apigateway.amazonaws.com` invocation permissions. SourceAccount and SourceArn restrict invocation to the supplied API, `$default` stage, and feature paths. No Function URL or public invocation principal is created. Remove feature-owned attachments on cleanup while preserving supplied infrastructure.

**Rationale**: ECR must exist before publishing. A direct AWS_PROXY integration can invoke the alias through payload format `2.0`. Stable alias movement preserves the gateway endpoint. DeploymentRevision publishes application code/environment changes; external Cognito/MCP client credential rotation remains independent and is not reversed by application rollback; provider environment lifecycle follows decision 11.

**Limits decision**: HTTP API integration timeout is at most 30 seconds. Set integration timeout to 30000 ms, Lambda timeout to 25 seconds (configurable 1–25), and client response deadline to 35 seconds, with a 10-second connection limit. Cold initialization consumes gateway time; never advertise the old 120/150-second settings as an end-to-end allowance. The six-MiB Lambda buffered invocation envelope, including headers/encoding/adapter overhead, remains tighter than the gateway's 10-MB payload quota. Record timeout/size failures rather than returning partial success.

**Alternatives considered**: REST API integration or named-stage/custom-domain support would add a different deployment profile; they are outside this initial plan. Function URLs conflict with gateway-only public access. Wildcard API/stage/path permissions weaken the boundary. Mutable image tags and out-of-band alias changes weaken release identity and rollback.

**Sources**: [CloudFormation integration](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-apigatewayv2-integration.html), [Lambda permission](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-lambda-permission.html), [API Gateway invocation](https://docs.aws.amazon.com/lambda/latest/dg/services-apigateway.html), [HTTP API quotas](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-quotas.html), [Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html), [image deployment requirements](https://docs.aws.amazon.com/lambda/latest/dg/images-create.html).

## 8. Publish through a separate opt-in OIDC workflow

**Decision**: Add a manual ECR publication workflow, isolated from the existing GHCR workflow. Use exact-repository/branch-or-environment OIDC trust, repository-scoped upload actions, and global ECR token retrieval only where required. Publish after local/unit/native-container gates; do not deploy automatically.

**Rationale**: This preserves current release triggers/tagging and avoids long-lived AWS keys. Operators explicitly select deployment region/account and bootstrap the service publishing role through planned publishing-iam.yaml; reuse/retention of an existing GitHub provider is explicit.

**Alternatives considered**: Replacing the existing workflow violates compatibility; granting administrator access for publication is unnecessary; automatically deploying each image changes the operational authorization scope.

**Source**: [AWS OIDC role guidance](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create-for-idp_oidc.html).

## 9. Separate deterministic verification from live provider behavior

**Decision**: Local fixtures patch provider boundaries while retaining real handlers and serialization. Compare full paginated tool discovery against an immutable pre-feature baseline_ref/catalog captured before implementation in a planned baseline manifest; run baseline code/image from its isolated pinned revision instead of comparing only two candidate transports. Live interactions use the existing deterministic `futures_watchlist` tool on the exact release image; separately report a live market request.

**Rationale**: Source inspection confirms `get_futures_watchlist` returns bundled constants without a network call. `exchanges_list` is a resource, not a tool, so it cannot count as a successful tool invocation. Market-provider outages must not masquerade as session/concurrency failures. Test-only fixtures are not shipped as a production environment switch.

**Alternatives considered**: Twenty external market requests add upstream rate/availability noise. A fake-provider production flag risks returning fixture data to users. Matching current market prices across deployments is not reproducible.

**Sources**: `server.py:futures_watchlist`, `core/services/futures_service.py:get_futures_watchlist`, existing annotation/offload/error-envelope tests.

## 10. Require evidence for cold starts and deployment success

**Decision**: Observe at least two distinct fresh execution environments using correlated CloudWatch startup/REPORT evidence, version/release identity, and log streams. Count only startup requests joined through gateway/integration and platform request IDs to a successfully completed MCP interaction in this run/release/target. Initialization/discovery may cause startup; health-only or unrelated starts are excluded. Record sanitized completed-interactions.json stage evidence and enforce these joins in semantic combine validation. The verifier reads AWS state only. If normal requests do not yield sufficient evidence, operators can create two disposable runtime stacks with the same digest; otherwise cold_start is not_run. Additional runtime stacks need separate supplied compatible APIs/authorizers because the feature route paths cannot be owned twice in one API.

**Rationale**: Two sessions, elapsed idle time, or a local process restart do not establish Lambda cold starts; two health-only startup records also do not prove SC-003's completed-interaction coverage. A schema-validated report records every required stage and only claims full success when all are evidenced.

**Alternatives considered**: Forcing configuration changes inside an ostensibly read-only verifier hides mutations. Treating absent cloud credentials as passing would violate the spec. A distinct fixture image is unnecessary for deterministic live tool/session checks and would not validate the actual production image.

**Sources**: [Lambda execution environments](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html), [cold-start measurement](https://aws.amazon.com/blogs/compute/building-well-architected-serverless-applications-optimizing-application-performance-part-1/), [Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html).

## 11. Use native Lambda environment variables for now

**Decision**: The user's current choice is direct native Lambda environment variables for all nine existing `.env.example` keys. CloudFormation maps ordinary inputs and optional NoEcho string parameters MarketauxApiToken, ProxyUsernamePrefix, and ProxyPassword (empty defaults) to the existing keys. Operators provide sensitive values through the parameter UI or a private JSON input file outside the checkout/artifacts; no application startup hook or configuration-fetching dependency is added.

**Rationale**: Lambda makes configured strings available before process startup, and the existing code already reads them. This keeps deployment configuration simple and removes external store availability, network reads, SDK packaging, and provider read/decryption permissions from startup. The application role retains scoped log writes only. Incoming MCP access continues through externally supplied Cognito/API Gateway authorization.

**Lifecycle/tradeoff**: Published function versions snapshot environment values. Changing a token/password/setting requires a function configuration update, fresh DeploymentRevision, publication, and verification, without rebuilding the image. Rollback restores prior provider values; expired/revoked values require a forward update using the known-good image. Configuration readers can access real provider values, and NoEcho does not mask metadata/outputs, so do not record full environment responses, credential values/hashes, or secret-bearing files in logs/artifacts. All configured values share the 4-KB quota.

**Compatibility**: Existing environment readers/defaults, optional provider fallback, and process-local daily budget remain unchanged. Native values need no shell evaluation, `.env` file, retrieval hook, Lambda-only SDK group, or new runtime permission. Local fixtures use synthetic values; live reports record only nonsecret settings/configuration revision and sanitized evidence.

**Alternatives considered**: External configuration storage and startup retrieval are deferred by the user's current scope choice. Image-embedded credentials, command-line plaintext credentials, committed environment files, and out-of-band stack configuration drift are excluded from the deployment workflow.

**Sources**: Repository `.env.example`, `core/services/proxy_manager.py`, and `core/services/marketaux_service.py`; [Lambda environment configuration and versioning](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html), [CloudFormation NoEcho semantics](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/parameters-section-structure.html), [CLI deploy parameter-file formats](https://docs.aws.amazon.com/cli/latest/reference/cloudformation/deploy.html).

## 12. Keep default CI independent of optional verifier tooling

**Decision**: Keep AWS/lint imports lazy in the verifier and retain default Python 3.10–3.13 unit collection without optional AWS dependencies. Add a separate planned Python 3.11 push/PR deployment-test job with the explicit deployment group, hermetic verifier/infrastructure/report tests, and lint. Ensure the frozen baseline revision is available in CI. Missing required dependencies or selected tests fail this dedicated job; they are not silently skipped.

**Rationale**: The existing test workflow installs normal development dependencies and discovers tests/unit. The locked MCP SDK already supplies JSON Schema validation transitively, but AWS/lint tooling belongs to an optional group. Explicit import/test boundaries avoid accidental collection failures while ensuring the new deployment checks actually run. No production runtime dependency or AWS credential is introduced.

**Alternatives considered**: Installing all optional AWS tooling into application dependencies expands runtime scope; allowing missing dependencies to skip required deployment tests hides coverage gaps. Baseline comparisons derived from candidate files can miss shared regressions and are rejected.

**Sources**: Repository `.github/workflows/test.yml`, `pyproject.toml`, and `uv.lock`.

## Research Completion

The service interface is defined; sibling access/billing lifecycle details are owned by their separate specs. Infrastructure choices, the supplied HTTP API integration profile, external auth/client scope, application/provider environment mapping, effective limits, lifecycle, test boundaries, and evidence requirements are defined. Gateway authorization is a live-only verification stage requiring denial-before-service and no-public-bypass evidence. Keep adapter DEBUG logging disabled because its debug request-header output can reveal authorization values. No upstream image digest, cloud resource, successful test result, benchmark, or authorization state has been fabricated. The placeholder constitution and lack of live validation are explicitly recorded in the plan.


## Feature Ownership — 2026-11-03

The service-only boundary is authoritative: [spec 002](../../../mcp-auth-subscriptions/specs/002-authentication-api-access/spec.md) owns Cognito/PKCE, gateway, custom authorizer, existing API adoption and subscription gating. [Spec 003](../../../mcp-auth-subscriptions/specs/003-billing-subscriptions/spec.md) owns a separate billing Lambda, Stripe integration and DynamoDB. No Stripe/DynamoDB SDK, client-token verifier, entitlement query or billing permission is added to the MCP runtime. The service publishing IAM stack remains in spec 001 because it supports only service artifact publication. Shared feature contracts and migration history are in [the feature index](../README.md) and [scope map](../scope-migration.md).
