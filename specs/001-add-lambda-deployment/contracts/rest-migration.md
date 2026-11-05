# Contract: Service Handoff to the REST Access Profile

**Status**: Planned service follow-up, not implemented. User chose REST native usage plans on 2026-11-03; [spec 002 gateway contract](../../../../mcp-auth-subscriptions/specs/002-authentication-api-access/contracts/rest-gateway.md) owns that new profile. Existing HTTP API resources/verifier/report v1 remain legacy, without implying REST support is delivered.

## Preserve and extend service transport only

Preserve existing 39 tools, stateless buffered JSON MCP, finite notifications, internal readiness, exact public-host checks, ARM64 pinned adapter/image, native Lambda provider variables, 25-second default timeout and original Docker/stdio/GHCR behavior. No JWT/OAuth/Stripe/DynamoDB/key-provisioning/signing logic, credentials, SDK or IAM enters the MCP process. Public 401 discovery and login/payment routes live upstream.

Add planned `infra/lambda/runtime-rest.yaml` containing service function/log/log-only role/native environment/version/live alias and release outputs, not API resources/methods/integrations/authorizer/native plans/invocation permissions. Supply exact REST hostname from base API ID/region, then output exact alias/version/image/log identity to access. A base API may exist without a deployment; service startup cannot require access/billing availability. Gateway creates all REST invocation permissions and attachments once aliases exist, then deployment/named stage. Access detaches its attachments before service cleanup.

Test the actual pinned Lambda Web Adapter against REST-v1 events: stage vs path, exact canonical /mcp, headers/multivalue headers/query/base64/body, finite notifications, unsupported methods, host rejection, JSON content-type and no SSE/session behavior. Simulated Runtime API events should exercise the packaged adapter, not only ASGI. Configure optional base-path removal only when proven necessary by representative REST events; do not blindly strip a stage already absent from event.path. REST slash edge behavior must be tested/documented by access without fabricating an empty path resource. Keep local slash normalization. REST integration deadline is 29 seconds; cold initialization shares that window.

## Report compatibility and verification

Do not alter [verification-report.schema.json](verification-report.schema.json): its report v1 and 16-stage semantics describe legacy HTTP API2.0/$default/route IDs. Add a planned `contracts/verification-report-v2.schema.json` for explicit REST API/named-stage/resource/method/deployment/authorizer/integration/permission provenance and REST-v1 transport. Reject cross-profile schema/data confusion. Preserve every existing mandatory verification stage, privacy, release identity, successful-interaction cold-start joins, thresholds, lifecycle and honest not_run rules. Report version/profile selection must be explicit; v1 local/live evidence cannot establish REST readiness.

Extend preflight/read-only service verifier separately for REST observations and exact function/alias comparisons, coordinated gateway output resolution and upstream denial/challenge/no bypass. Access verifier separately proves OAuth/grants/subscriber-key mapping; service verifier does not implement identity or billing policy. Preserve legacy CLI/input/report behavior; no direct Lambda mutation/invocation for public security proof.

## Migration and acceptance

Keep runtime.yaml/legacy HTTP endpoint available under its documented profile until explicitly scoped cutover. New REST API ID and stage-prefixed endpoint differ; client resource/grant audience must be reconfigured through access. Validate actual host/access/transport/payment/metering before cutover and keep every active legacy path secured or disable it via access-owned action. No automatic replacement/deletion or insecure rollback. Prior 516 local tests remain historical HTTP/service evidence.

All new work is pending [T051–T055](../tasks.md); original T001–T050 task lines/states and reviewer checklists remain preserved. Local-only instruction means live REST deployment, denial, cold/lifecycle and cutover checks remain not_run until real prerequisites are available.
