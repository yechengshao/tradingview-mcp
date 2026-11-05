# Data Model: Lambda Deployment

**Profile revision — 2026-11-03**: The user selected REST API with native usage plans. The [REST service handoff](contracts/rest-migration.md) governs the new target and supersedes any HTTP-only exclusion below for future work. Existing HTTP API v2/`$default`/payload2.0 routes, commands and report-v1 details below describe the delivered **legacy HTTP profile**, not an implemented REST deployment. New service-only runtime/report-v2 work is pending; spec 002 owns all new REST attachments and invoke permissions.

This feature adds deployment/integration and verification records, not a business database. Existing tool inputs/results and bundled coinlists retain their schemas. Spec 002 owns Cognito/gateway/custom-authorizer identities and policy. Spec 003 owns Stripe billing and DynamoDB entitlement data. This service model has no customer/subscription entities or identity/billing runtime configuration.

## Release Artifact

| Field | Meaning / validation |
|---|---|
| source_commit | Full source commit identifier, recorded in image labels and build evidence |
| source_dirty | Whether build inputs contained uncommitted source changes; report explicitly |
| dependency_lock_sha256 | Lowercase 64-hex digest of the build's `uv.lock` |
| image_config_digest | OCI configuration digest binding the tested local image to the registry manifest |
| image_uri | Same-account/same-region ECR repository plus immutable `@sha256:` manifest digest |
| architecture | Exactly `arm64` / build platform `linux/arm64` |
| release_tag | Unique immutable publishing tag, never reused for different content |
| adapter_version / builder_version | Adapter 1.1.0 and uv 0.13.1; resolved upstream image identities recorded during build |

Many deployments can reference one artifact. Build once, test locally, then push the same image. Registry manifest `config.digest` must match local image evidence.

## Compatibility Baseline

`tests/integration/support/baseline.json` is a planned committed fixture, not generated deployment evidence. It records baseline_ref as the full pre-feature commit SHA, frozen before implementation/tooling changes (default initial HEAD), and captures complete paginated tool descriptors, original Docker/stdio commands/health contract, original publishing triggers/destination/architectures/tag rules, and capture/dependency identity from that pinned revision. Capture and execute baseline code in an isolated checkout/archive; never infer expected values from the candidate. Missing reference/provenance is an explicit verification error, not a fallback to current HEAD. Both transports drifting together must still fail against the immutable catalog/behavior contract.

## Deployment Configuration

| Field / stack parameter | Default / validation |
|---|---|
| Region | Explicit commercial AWS region; example `ca-central-1`; API, ECR, and function share account/region |
| RepositoryName | Explicit project-owned ECR repository; example `tradingview-mcp-lambda` |
| Runtime stack name | Letter-led alphanumeric/hyphen name, at most 48 characters; also names function/log group |
| ImageUri | Immutable release artifact ECR digest |
| DeploymentRevision | Unique 1–64 character alphanumeric/dot/underscore/hyphen value for each application code/environment publication |
| SourceCommit / LockSha256 | Match build evidence and image labels |
| ApiId | Supplied existing HTTP API v2 ID; lowercase alphanumeric; execute-api endpoint enabled |
| AuthorizerId | Supplied REQUEST custom authorizer in that API; Authorization-header identity input; Cognito-backed policy owned externally |
| MemorySize | 1024 MiB; validate supported Lambda range |
| TimeoutSeconds | 25; integer 1–25, within the 30-second gateway integration window |
| EphemeralStorageMb | 512; supported Lambda range 512–10240 |
| ReservedConcurrency | 5; positive integer; verify quota capacity before deployment |
| LogRetentionDays | 14; supported CloudWatch retention value |
| RollbackVersion | Empty for new publication; otherwise retained numeric version of this function |
| MarketauxApiToken / ProxyUsernamePrefix / ProxyPassword | Optional strings, default empty; NoEcho true on all three deployment parameters; mapped directly to native Lambda environment variables |
| MarketauxDailyBudget | 90; nonnegative integer, serialized as a string |
| ProxyEnabled | `true`; literal `true` or `false` string |
| ProxyHost / ProxyPort | `p.webshare.io` / 80; nonempty hostname and integer port 1–65535 |
| ProxySessionMin / ProxySessionMax | 1 / 250; positive integers with minimum no greater than maximum |

The supplied stage is fixed to `$default` with AutoDeploy true in the initial profile; neither stage nor API is provisioned. Integration timeout is 30000 ms. External clients use a 10-second connection limit and 35-second response deadline; cold initialization shares the gateway window. Named stages, REST APIs, and custom-domain mappings are not supported by this initial integration profile.

Runtime environment contains release/revision identity, TRADINGVIEW_MCP_PUBLIC_HOST (exact execute-api authority derived from ApiId/region), AWS_LWA_PORT=8000, AWS_LWA_READINESS_CHECK_PATH=/health, AWS_LWA_READINESS_CHECK_HEALTHY_STATUS=200, AWS_LWA_INVOKE_MODE=buffered, the nine application settings below, and Python writable-path settings. AWS supplies AWS_REGION; do not set reserved Lambda variables. Lambda supplies these configured values before process startup. There is no startup retrieval hook, provider SDK dependency, or provider-storage read permission. Provider credentials are separate from MCP client authentication; client bearer credentials are not injected into the service.

State: repository_bootstrapped → image_published → function_created_or_updated → version_published → alias_active → gateway_attached → verified. Failure requires explicit operator rollback. Cleanup removes feature attachments/runtime before optional ECR removal.

## Existing Application Environment Mapping

Use native Lambda Environment.Variables for all nine existing `.env.example` keys. The file is a naming reference only; it and `.env` are not packaged or read at Lambda startup. Existing application code reads the already available values through its environment readers.

| Runtime environment key | Deployment parameter | Default / behavior |
|---|---|---|
| MARKETAUX_API_TOKEN | MarketauxApiToken (NoEcho) | Empty; preserves current no-news-provider fallback |
| MARKETAUX_DAILY_BUDGET | MarketauxDailyBudget | `90`; per execution environment/process, not a shared daily quota |
| PROXY_HOST | ProxyHost | `p.webshare.io` |
| PROXY_PORT | ProxyPort | `80` |
| PROXY_USERNAME_PREFIX | ProxyUsernamePrefix (NoEcho) | Empty; proxy remains unavailable without both prefix and password |
| PROXY_PASSWORD | ProxyPassword (NoEcho) | Empty |
| PROXY_SESSION_MIN | ProxySessionMin | `1` |
| PROXY_SESSION_MAX | ProxySessionMax | `250` |
| PROXY_ENABLED | ProxyEnabled | `true`; existing behavior additionally requires configured prefix/password |

All values are literal NUL-free strings, available before service imports; do not expect shell interpolation. Validate nonnegative budget, literal true/false, nonempty host, port 1–65535, and positive ordered session bounds. All configured values—including credentials, adapter/release settings, and application configuration—share Lambda's combined 4-KB environment quota. Report size/range failures without logging values. Missing optional provider credentials preserve existing fallback; startup and health do not contact a configuration store or market provider.

Credential deployment parameters have NoEcho true and empty defaults. Operators supply values through CloudFormation's parameter UI or a private mode-0600 JSON parameter file outside the checkout/build context and verification evidence directory; CLI commands reference the file path rather than raw values. Do not print the file, enable CLI/shell debug tracing, commit it, or include it in artifacts/reports. Remove temporary input files after deployment; ongoing source credential storage is the operator's responsibility. NoEcho masks stack parameter displays but does not protect template/resource metadata, outputs, or authorized Lambda configuration reads, so credentials must never be copied there. The native environment contains real provider credentials; configuration readers must be appropriately scoped. Do not add a separate credential-storage service, runtime fetch, or provider decryption grant in this phase.

Published Lambda versions snapshot code and environment values. A provider-token/password or other environment change requires a function configuration update, fresh DeploymentRevision, published version, and verification; no image rebuild is required. Alias rollback restores the earlier environment snapshot, whose provider credentials may have expired/revoked externally. If invalid, deploy the known-good image with current provider values and a new revision. Cognito/MCP client credential rotation remains independent and is not restored by application rollback. Update the complete intended environment map through the stack, preserving adapter/release keys and any unchanged credential inputs; do not introduce out-of-band configuration drift.

## Supplied Access-Control Infrastructure

| Field | Ownership / validation |
|---|---|
| api_id, stage_name | Existing HTTP API and `$default` auto-deploy stage; read-only prerequisites |
| authorizer_id | Spec 002 custom authorizer plus its invocation permission, Cognito policy and subscription enforcement; the MCP service consumes only its identifier |
| credential instructions | Owner supplies acquisition, refresh, expiry/revocation, accepted header/token policy; no user/account entity is added here |
| access-log evidence location | Owner supplies sanitized gateway correlation evidence sufficient to prove denial before service invocation |

For MCP access control, only access identifiers/integration requirements enter deployment configuration; no Cognito client secrets, Stripe credentials, billing table name or customer/subscription data enters the MCP environment. Raw MCP client credentials stay in the client's or live verifier's external environment, never in the application environment or stack parameters/outputs. Provider credentials are a separate category, supplied directly through native Lambda environment configuration as defined above. Neither category may appear in an image, tracked file, deployment output, or report. External MCP client credential rotation does not publish a service version; service rollback does not restore those client credentials or external authorization policy.

## Published Deployment / Gateway Attachment

| Field | Meaning |
|---|---|
| stack_id, account_id, region | Scope/ownership for control-plane operations |
| function_arn, version, alias_arn | Exact function/version and stable `live` alias |
| api_id, stage_name, authorizer_id | Supplied access-control identifiers; stage is `$default` |
| integration_id, route_ids | Feature-owned AWS_PROXY payload-2.0 integration plus exactly three routes: `ANY /mcp`, `ANY /mcp/`, `GET /health`, all CUSTOM |
| api_endpoint, mcp_endpoint, health_url | Supplied API's execute-api HTTPS base URL and `/mcp`, `/health`; no credentials or Function URL |
| resolved_image_uri | Digest actually reported by Lambda for the alias's active version |
| log_group_name | Project-owned Lambda log group for diagnosis/cold evidence |

Publish a new version for application code/environment changes using DeploymentRevision, retain replaced versions, and move the alias through CloudFormation. Feature routes are reserved by the API owner across stages; alias permissions authorize only `$default` stage method/path patterns. No API, stage, authorizer, Cognito resource, or unrelated route is imported into feature ownership. Cleanup removes only feature-owned integration/routes/permissions and runtime resources.

## Verification Run

Authoritative contract: [verification-report.schema.json](contracts/verification-report.schema.json).

- Run ID/UTC timestamps identify the validation attempt. Source/lock/config/manifest digests bind local and live evidence.
- Target includes gateway provenance; local/incomplete targets may use `gateway: null`. AWS targets record the supplied API/stage/authorizer and feature integration/route IDs. Additional cold-evidence targets use separate supplied compatible APIs.
- Each mandatory stage has `pass`, `fail`, or `not_run` plus evidence/reason. Local authorization is always `not_run`; an unauthenticated local service cannot prove gateway authorization.
- `authorization_evidence` is null until observed. A passing authorization stage includes missing/invalid credential denials (optional expired case), 401/403 responses, gateway request IDs, `service_invoked: false`, sanitized correlation references, `public_bypass_absent: true`, and configuration evidence. Verify every feature route, alias permission scope, absent Function URLs, and absence of other public paths. External policy errors (for example 500) are failures, not valid credential denials.
- Application-configuration evidence records supported key names, nonsecret settings, and the applicable configuration revision only, never credential values or hashes. Additional targets must use the same intended provider configuration and nonsecret settings; public-host/API identifiers may differ as required by their separate gateways. Existing artifact_startup, release_identity, release_lifecycle, and documentation_walkthrough stages cover this configuration without a new report-schema field.
- Counts track completed interactions, concurrent clients, successful health probes, and evidenced fresh starts. Full success requires all mandatory stages and thresholds plus lifecycle/documentation evidence.
- Evidence never stores raw Authorization headers, tokens, claims, signed headers, presigned URLs, or unrestricted logs. Gateway identifiers alone are not proof that authorization works.

A ColdStartEvidence record binds target ARN/version, distinct execution-environment log stream, platform request ID, observation window, and initialization duration to the tested release. Every record counted toward SC-003 must additionally join to a request within a successfully completed initialization/discovery/tool interaction in this run. The request causing startup may be any of those MCP stages; it need not be the tool call. Gateway/integration evidence must map that client request to the same Lambda platform request/environment; a health/readiness request or unrelated start is ineligible.

Planned `completed-interactions.json` stage evidence contains interaction_id, completed_success, and sanitized MCP request records with stage (initialization, discovery, or tool_execution), gateway_request_id, platform_request_id, function_arn, function_version, log_stream, and observed_at plus correlation evidence references. Record complete success only after all required stages finish. Do not retain request/result bodies, credentials, or health calls in that completed-success set. Bind this sidecar via the existing stage evidence ref and SHA-256 fields; the main report schema/stage names stay unchanged. The semantic validator derives evidenced_fresh_starts from distinct cold records joined to this completed-success set, matching run window/release/target. Missing joins remain not_run/incomplete; two raw startup records alone cannot establish success. Fewer than two evidenced starts means cold_start is not_run unless an attempted check establishes failure. Lifecycle evidence must show supplied infrastructure survives cleanup while feature-created attachments disappear.


## Cross-Feature Ownership

API/authorizer outputs come from [spec 002](../../../mcp-auth-subscriptions/specs/002-authentication-api-access/spec.md). The authorizer uses the [spec 003 entitlement interface](../../../mcp-auth-subscriptions/specs/003-billing-subscriptions/contracts/entitlements.md); the MCP function neither consumes that interface nor needs DynamoDB/Stripe permissions. The service publishing role has ECR-only permissions and explicit account-level OIDC reuse/retention. Exact runtime/function identity must be distinguished from other feature functions even when names share a prefix; unrelated billing integrations cannot be mistaken for MCP bypass paths.
