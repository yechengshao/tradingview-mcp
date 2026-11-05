# Spec 001: MCP Service on Lambda

**Created**: 2026-10-18 · **Updated**: 2026-11-03 · **Branch**: `main`
**Status**: Legacy HTTP runtime delivered locally; publishing IAM, REST support and live acceptance pending.

## Scope and confirmed decisions

Run the existing 39 TradingView MCP tools on Lambda while preserving Docker, local transport and GHCR releases.

- Service handles finite, stateless JSON request/response interactions and internal health checks.
- [Spec 002](../../../mcp-auth-subscriptions/specs/002-authentication-api-access/spec.md) owns Cognito, Step Functions onboarding, REST API, authorization and usage plans. [Spec 003](../../../mcp-auth-subscriptions/specs/003-billing-subscriptions/spec.md) owns billing Lambda/DynamoDB/Stripe.
- MCP implements no authentication/billing and receives no related credentials, storage access or permissions.
- All nine provider settings use native Lambda environment variables; no startup retrieval hook.
- REST is the new target. Existing HTTP API implementation/report v1 remains a separate legacy profile; see [REST handoff](contracts/rest-migration.md).
- Long-lived streams, server notifications, persistent sessions and new tool business logic are outside scope.

## User scenarios and acceptance

### Story 1 — Use remote tools (P1)

An authorized client initializes, discovers the complete catalog and executes tools across cold starts, replacement and concurrent instances. Controlled results match the existing server; unauthorized requests never invoke MCP. Each interaction completes without a persistent stream or shared session state.

### Story 2 — Preserve existing deployments (P1)

Original Docker commands, ports, health and tool behavior remain compatible. Local transport needs no AWS configuration. Existing image destinations, architectures and tags remain unchanged.

### Story 3 — Operate from documentation (P2)

A reviewer uses a clean checkout to deploy, connect, verify, update, roll back and clean up a named test installation. Missing permissions/artifacts/configuration produce actionable diagnosis; unrelated access/billing resources survive cleanup.

### Story 4 — Verify readiness (P2)

Health confirms server availability without market-provider calls. Verification distinguishes startup, connectivity, authorization, provider and platform-limit failures, recording release/target and stage results without credentials.

**Edge cases**: unsupported methods/streaming clients; invalid tools/inputs; provider failure or changing prices; wrong artifact/region; oversized/slow responses; read-only storage; cross-request data mixing. Test parity with controlled providers; record live provider observations separately.

## Functional requirements

- **FR-001**: Add a documented Lambda deployment option for the existing MCP service.
- **FR-002**: Expose a secure remote endpoint supporting authorized initialization, discovery and tool execution.
- **FR-003**: Preserve tool names, descriptions, schemas, annotations, result structures and errors; compare values using controlled providers.
- **FR-004**: Support stateless request/response across cold starts, replacement and concurrency; exclude long-lived streams and server-initiated notifications.
- **FR-005**: Consume spec 002's Cognito/custom-authorizer access boundary. Deny unauthorized callers upstream, prohibit public bypasses and keep credentials out of artifacts/configuration/evidence.
- **FR-006**: Preserve Docker startup/networking/health/tools and existing local launch behavior without AWS configuration.
- **FR-007**: Preserve existing publishing destinations/architectures/tags; document additional Lambda artifact publication.
- **FR-008**: Provide documented health location/result, independent of market-provider success.
- **FR-009**: Document prerequisites, permissions, provider/access configuration, build/publication, deployment/endpoints, client connection, verification, updates, rollback and cleanup.
- **FR-010**: Document duration, response-size, storage and client/session limits, including unsupported streaming/notification capabilities.
- **FR-011**: Independently verify startup, health, initialization, complete discovery, successful tool execution, upstream authorization/no bypass, invalid input, provider failure, cold starts and concurrency.
- **FR-012**: Verify original Docker/local compatibility and relevant existing automated tests.
- **FR-013**: Report release, target and pass/fail/not_run per stage; missing live checks cannot establish deployment success.
- **FR-014**: Provide credential-safe logs and diagnosis for startup, authorization, connectivity, platform limits and provider failures.
- **FR-015**: Limit lifecycle actions to owned resources. Preserve access/billing; access detaches REST attachments before service removal. Legacy HTTP attachments remain service-owned.
- **FR-016**: Reproduce service ECR publication using repository-scoped temporary GitHub OIDC credentials with no deployment/billing-data rights.
- **FR-017**: Keep identity validation, billing processing/state and related SDK/configuration/IAM outside MCP; internal readiness remains independent of those systems.

## Success criteria

- **SC-001**: A clean-checkout reviewer completes documented deployment, connection, verification, update, rollback and cleanup with supplied access prerequisites and no source edits/unpublished steps.
- **SC-002**: Complete discovery has zero descriptor differences; controlled success/error results preserve established behavior.
- **SC-003**: Complete at least 20 initialization→discovery→tool interactions, across two evidenced fresh environments and a five-client burst, with zero state/data-mixing failures.
- **SC-004**: Every unauthorized test invokes MCP zero times; no public bypass or credential exposure exists.
- **SC-005**: Ten consecutive warm health checks each finish within five seconds with zero provider calls, including simulated provider failure.
- **SC-006**: Docker/local and relevant automated checks pass; original publishing destinations, architectures and tags remain unchanged.
- **SC-007**: Every mandatory stage has a result; full deployment success requires all required live stages to pass.
- **SC-008**: Local build/start/verification needs no Cognito/Stripe/DynamoDB configuration; runtime IAM/environment exclude identity/billing access and cleanup preserves sibling resources.

## Assumptions and references

Operators supply account/region, permissions, optional provider values and eligible external credentials for live checks. Local-only validation is the current instruction; absent live checks remain not_run. Acceptance counts are minimum checks, not an SLA. The constitution is an unfilled template.

[Plan](plan.md) · [Tasks](tasks.md) · [Configuration/evidence model](data-model.md) · [Deployment contract](contracts/deployment.md) · [Operator guide](../../docs/lambda-deployment.md)
