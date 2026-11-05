# Contract: Lambda MCP HTTP Interface

**Profile revision — 2026-11-03**: The user selected REST API with native usage plans. The [REST service handoff](rest-migration.md) governs the new target and supersedes any HTTP-only exclusion below for future work. Existing HTTP API v2/`$default`/payload2.0 routes, commands and report-v1 details below describe the delivered **legacy HTTP profile**, not an implemented REST deployment. New service-only runtime/report-v2 work is pending; spec 002 owns all new REST attachments and invoke permissions.

## Scope

Applies only to the planned Lambda entrypoint. Existing Docker and local transports retain their contracts. The supported initial public path is a spec-002-owned API Gateway HTTP API v2, enabled execute-api endpoint, auto-deploy `$default` stage, and Cognito-backed REQUEST custom authorizer. The service implements no MCP client authentication or billing. The custom authorizer enforces subscriptions using the entitlement interface owned by spec 003 before forwarding MCP requests. Optional upstream market-data/proxy credentials are supplied through native Lambda environment variables for existing tool behavior; they do not authorize callers to this endpoint. Clients obtain/refresh credentials through the supplied infrastructure's documented flow; this feature adds no OAuth discovery/login endpoints, user management, or token verifier.

The endpoint supports request-and-response MCP initialization, discovery, and tool calls. Long-lived streams, server-initiated notifications, persistent sessions, resumability, session affinity, browser/CORS flows, REST API integration, named stages, and custom-domain mappings are outside this initial profile. Finite client-to-server MCP notifications remain supported.

## Routes and Results

| Request | Public gateway policy | Service result after gateway acceptance |
|---|---|---|
| `GET /health` | Supplied CUSTOM authorizer | 200, `application/json`, exact object `{"status":"ok"}`; no provider calls |
| `POST /mcp` | Supplied CUSTOM authorizer | Successful JSON-RPC replies: 200, `application/json`; accepted notifications may be 202 with no body per SDK behavior |
| `POST /mcp/` | Supplied CUSTOM authorizer | Internally normalized to `/mcp`; no external redirect |
| Unsupported method on `/mcp` or `/mcp/` | Supplied CUSTOM authorizer | 405, `Allow: POST`; no stream opened |
| Missing/invalid client credential | Rejected before service invocation | No service response; gateway/authorizer normally returns 401 or 403 according to its supplied policy |
| Unknown public route / unsupported health method | Existing gateway routing policy | Must not invoke this service through an unauthorized alternate route; exact error shape belongs to supplied gateway |

Create `ANY /mcp`, `ANY /mcp/`, and `GET /health`, all AuthorizationType CUSTOM with the supplied AuthorizerId. Reject existing exact/method-specific route conflicts; do not overwrite them. The direct backend uses AWS_PROXY, integration method POST, payload format `2.0`, targeting the `live` alias. No Function URL is created.

Local container/adapter requests have no service authentication; `GET /health` is available on loopback for readiness, and MCP requests can be tested without an Authorization header. This internal behavior cannot establish public security. Gateway denial body, WWW-Authenticate headers, and credential parsing are not service contracts. Malformed authorizer configuration/500 responses must be diagnosed as configuration failure, not accepted as successful unauthorized rejection.

## Authorization Boundary and Ownership

The operator supplies Cognito configuration, HTTP API, `$default` auto-deploy stage, custom authorizer, its invocation permission, supported identity header/token policy, and client credential lifecycle instructions. The feature creates only integration/routes and narrowly scoped backend invocation permissions. It does not create or modify the supplied authorization resources or validate MCP client credentials in service code.

Invoke permissions apply only to the `live` alias, principal `apigateway.amazonaws.com`, the deployment SourceAccount, and SourceArn patterns for the supplied API, `$default` stage, and feature method/path combinations. No public principal, public Function URL, or alternate unauthenticated route may reach the backend. Inspect deployed API routes/integrations and function/alias policies; do not infer this property from endpoint possession or a single denied HTTP call.

All feature routes, including external health, use the supplied authorizer. Unauthorized MCP discovery/execution must never invoke this service (the separate authorizer Lambda may run). Verification correlates gateway request/access records with integration/Lambda evidence. External credential issuance/rotation/revocation remains outside application release/rollback.

## Authority, Origin, and Logging

- Supply the exact expected public authority in nonsecret `TRADINGVIEW_MCP_PUBLIC_HOST`, validated before readiness. Use exact allowed authorities: loopback/readiness plus `<ApiId>.execute-api.<AWS_REGION>.amazonaws.com`, optionally `:443`.
- Keep SDK DNS-rebinding protection enabled; reject Origin headers for supported nonbrowser clients and ignore forwarded authority headers. Do not disable security globally or rewrite a Function URL hostname.
- HTTP API payload 2.0 combines duplicate headers. No raw-edge duplicate-header guarantee is made by the service; credential parsing belongs to the supplied authorizer.
- Lifespan scopes pass through transport wrappers unchanged; Uvicorn uses one worker with proxy headers disabled.
- Never log authorization headers, credential values, request-body secrets, or claims. Keep adapter DEBUG/header logging disabled. Reports use sanitized request/release identifiers and evidence references.

## Protocol and Compatibility

- Reuse all 39 existing decorated tools and existing resources, including paginated discovery. Do not copy a second catalog.
- Preserve names, descriptions, schemas, annotations, optional output schemas, and controlled result/error serialization against the immutable pre-feature baseline_ref/catalog; comparing only two candidate transports is insufficient.
- Set the locked SDK's stateless HTTP and JSON options before app creation; preserve its session-manager lifespan.
- Require no persistent Mcp-Session-Id or instance affinity; do not substitute SSE for complete JSON responses.
- Verify initialization, initialized notification, paginated listing, successful calls, invalid input/tool name, provider errors, and concurrent clients over the wire.
- Canonical public endpoint: `https://<ApiId>.execute-api.<region>.amazonaws.com/mcp`. Local container endpoint: `http://127.0.0.1:8000/mcp`.

## Limits and Diagnostics

The gateway integration timeout is 30 seconds; default Lambda timeout is 25 seconds (configurable 1–25), client response deadline 35 seconds, connection limit 10 seconds. Cold initialization shares the gateway window. These are failure bounds, not a guarantee every upstream request finishes in time. Buffered Lambda invocation envelopes allow at most six MiB including headers/encoding/adapter representation; do not advertise six MiB as guaranteed tool-body capacity. The gateway's larger payload quota does not remove that limit. No long-lived stream is used to bypass limits; size/time failures never count as partial tool success.

Health proves server availability, not upstream provider health or complete MCP connectivity. Distinguish gateway authorization, routing/permission, startup, platform-limit, and provider failures. Evidence requirements and exit codes are in [deployment.md](deployment.md).


## Feature split

[Spec 002](../../../../mcp-auth-subscriptions/specs/002-authentication-api-access/spec.md) owns Cognito human PKCE login, custom authorization, gateway/adoption and upstream subscription enforcement. [Spec 003](../../../../mcp-auth-subscriptions/specs/003-billing-subscriptions/spec.md) owns Stripe processing in a separate billing Lambda and DynamoDB. The MCP process continues to provide only existing tools/health/transport and does not read entitlement state. Billing ingress is never routed to the MCP alias; runtime cleanup preserves both sibling features.
