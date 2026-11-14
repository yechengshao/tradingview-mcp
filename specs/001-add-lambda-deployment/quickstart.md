# Quickstart: MCP Service Deployment

**REST steps**: see [REST service-only profile](../../../docs/lambda-deployment.md#rest-service-only-profile); this quickstart still describes the legacy HTTP profile.

**Profile revision — 2026-11-03**: The user selected REST API with native usage plans. The [REST service handoff](contracts/rest-migration.md) governs the new target and supersedes any HTTP-only exclusion below for future work. Existing HTTP API v2/`$default`/payload2.0 routes, commands and report-v1 details below describe the delivered **legacy HTTP profile**, not an implemented REST deployment. New service-only runtime/report-v2 work is pending; spec 002 owns all new REST attachments and invoke permissions.

**Updated**: 2026-11-03. Spec 001 is service-only: runtime, ECR/service image publication, native provider configuration and service publishing IAM. Identity/gateway/subscription authorization is owned by [spec 002](../../../mcp-auth-subscriptions/specs/002-authentication-api-access/spec.md); Stripe billing in a separate Lambda/DynamoDB is owned by [spec 003](../../../mcp-auth-subscriptions/specs/003-billing-subscriptions/spec.md).

## Delivery state and inputs

The MCP ARM64 image, ECR/runtime templates, manual service publication and local/live/combine service verifier are delivered. Publishing-IAM/interface follow-up is pending in T045–T050; service REST runtime/report follow-up is pending in T051–T055. The earlier 516 local tests cover the delivered service runtime, not newly planned access or billing behavior. Original T040/T044 cloud acceptance remains unperformed. The active feature remains spec 001.

Prepare account/region, explicit ECR/runtime names, access-provided ApiId/AuthorizerId/endpoint and optional upstream provider values. Local service checks require no identity/Stripe/DynamoDB configuration. A live service run needs an externally obtained identity/entitlement-eligible token; it does not create subscriptions or inspect billing state.

## Local service validation

```sh
uv sync --python 3.11 --dev --group deployment --locked
uv run --locked --group deployment pytest tests/unit -q
uv run --locked --group deployment cfn-lint infra/lambda/ecr.yaml infra/lambda/runtime.yaml
```

Build the candidate from the current checkout with source/dirty/root-lock labels and pinned ARM64 inputs. Build the original baseline image from the frozen baseline_ref archive with its source label; never regenerate expectations from the candidate. The [service operator guide](../../docs/lambda-deployment.md) has executable build/private-parameter instructions.

```sh
uv run --locked --group deployment python scripts/verify_lambda.py local \
  --baseline-image tradingview-mcp-baseline:test \
  --lambda-image tradingview-mcp-lambda:test \
  --report /tmp/tradingview-lambda-evidence/local.json
```

Local-only normally exits 2 because cloud stages are not_run. Require eligible local/native image and compatibility stages to pass. Missing native Docker/image prerequisites are unavailable; no emulated timing or fixture is live deployment evidence.

## Publication and runtime attachment

Bootstrap delivered ecr.yaml once. Planned publishing-iam.yaml creates only the exact-repository GitHub OIDC role with explicit provider reuse or create-and-retain; no deployment/billing/identity access is added. The existing manual service workflow builds/tests/pushes only the MCP image with immutable manifest/config identity, preserving GHCR behavior.

For the delivered legacy HTTP profile only, supply a compatible protected HTTP ApiId/AuthorizerId to runtime.yaml with the tested MCP digest/revision/native environment. Runtime owns its integration/three protected routes/backend alias permissions; it does not own gateway base/identity/billing resources. [The access integration contract](../../../mcp-auth-subscriptions/specs/002-authentication-api-access/contracts/service-integration.md) defines this boundary.

All nine existing provider settings remain native Lambda environment variables. Use private mode-0600 ParameterKey/ParameterValue inputs outside checkout/build/evidence, NoEcho for provider credentials, literal strings and a complete adapter/application/release map. Omitted update credentials preserve prior values; explicit empty strings clear them. No token retrieval hook/store/identity or billing configuration is added to MCP.

## Verification, rollback and cleanup

Keep the v1 service report/16 stages, exact gateway/integration/alias scope, finite JSON transport, source/lock/image identity, original Docker/stdio/GHCR compatibility, controlled provider errors and health checks. Real service checks require 20 complete interactions, five clients, two startup records joined to successful interactions, and ten timed health probes. Missing live prerequisites stay not_run.

MCP code/provider-setting updates and retained-version rollback change neither Cognito/authorizer policy nor subscriptions. Runtime cleanup removes only its own attachments/service resources and preserves access, billing data, identity/shared publishing resources and retained ECR images. Compare exact function identities when inspecting sibling billing/access integrations, even if names share a prefix. Service success does not establish payment or access-component readiness; those features have separate acceptance evidence.
