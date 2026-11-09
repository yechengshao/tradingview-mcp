# Plan 001: MCP Service on Lambda

**Updated**: 2026-11-08 · **Branch**: `main` · [Spec](spec.md) · [Tasks](tasks.md)

## Scope and profiles

Serve the existing 39 tools through an isolated ARM64 Lambda image while preserving original Docker/local/GHCR behavior and locked application dependencies. MCP implements no identity, billing, state-store retrieval or onboarding logic. Its role writes its own logs and conditionally exports traces.

| Profile | Status and ownership |
|---|---|
| Legacy HTTP API v2 | Implemented runtime.yaml owns payload-2.0 integration, MCP/health routes and alias permissions on the supplied API/authorizer |
| REST API | Pending runtime-rest.yaml supplies function/version/alias/logs/native environment; spec 002 owns attachments, permissions, named stage and usage plans |

[REST handoff](contracts/rest-migration.md) defines explicit secured cutover; legacy commands/report v1 cannot prove REST readiness. Specs 002/003 own access and billing in the sibling repository.

## Runtime and packaging

Use Python 3.11, pinned MCP 1.29.0, Starlette 0.47.2, Uvicorn 0.35.0, HTTPX 0.28.1, uv 0.13.1 and Lambda Web Adapter 1.1.0. Preserve advertised Python 3.10–3.13 ordinary transports. Monitoring adds no application dependency; native AWS tracing and stdlib-only CloudWatch logging preserve ordinary entrypoints.

lambda_server validates literal native environment before importing the singleton, enables stateless JSON/lifespan and runs one worker on port 8000. Preserve exact execute-api/internal hosts, DNS-rebinding protection, Origin rejection, disabled proxy-header trust, finite responses/notifications, POST-only MCP and slash normalization. Health stays provider-independent. No startup provider/configuration-store read or runtime uv/AWS application SDK.

Build one immutable native ARM64 image without attestations/index overhead; record source/dirty/lock/config/manifest identity, test under nonroot/read-only root with writable /tmp, then publish that same image. Emulation does not establish native timing.

## Configuration and lifecycle

[Data model](data-model.md) owns parameters/environment; [deployment contract](contracts/deployment.md) owns lifecycle and credential handling. Defaults: 1024 MiB memory, 512 MiB temporary storage, concurrency 5, log retention 14 days, timeout 25 seconds (1–25). Legacy gateway deadline is 30 seconds; REST is 29, including cold initialization. Client connect/response deadlines are 10/35 seconds; buffered envelopes stay within six MiB.

Map nine provider settings directly from NoEcho/private deployment inputs; preserve literal values, empty fallback and combined 4-KB environment validation. No secrets/hashes/full environment in outputs or evidence. DeploymentRevision changes for each code/environment publication; retained versions and alias rollback restore environment snapshots. Revoked credentials require forward revision with current values.

Order: service ECR → ECR-only OIDC publishing IAM → immutable image → runtime/version/alias → gateway attachment → verification. Preserve shared identities/access/billing; no Function URL/VPC/NAT/database. Cleanup owns legacy attachments, while access detaches REST wiring before service removal.

## MCP observability

Implement FR-018/SC-009 through the [observability contract](contracts/observability.md): Lambda-only JSON startup/request/tool failure logs, opaque correlation, available AWS trace IDs and safe stack locations. No arguments/results, URLs/headers or raw exception text are captured. No third-party telemetry SDK, exporter, custom span, collector or worker is used.

AWS-native Active tracing is explicit (default off); AWS controls Lambda invocation segments/sampling. Existing retention is configurable; development should choose three days. Conditional native X-Ray IAM grants no customer-data rights. Use native metrics/on-demand queries; spec 002 owns REST stage tracing and its 1% rule. Tool/dependency subsegments are not implemented; application failure timings stay in logs.

## Verification and evidence

Freeze original descriptors/source/launch provenance; compare candidate in isolated processes with controlled providers. Preserve report v1 bytes/all 16 stages; pending REST v2 requires separate provenance. Run unit/telemetry/transport/verifier/IaC checks; ordinary CI needs no telemetry extra, dedicated Lambda CI installs it.

Live acceptance still requires 20 complete interactions, five clients, two gateway/platform-correlated fresh environments and ten health checks under five seconds, plus denied-before-MCP/no-bypass and deploy/update/rollback/cleanup evidence. Missing checks remain not_run; prior 516-test evidence is historical. T056/T057 implement local observability; T058 retains native-image/cloud delivery/overhead acceptance. Reviewer checklists and existing task states remain unchanged unless their work is actually verified.
