# Plan 001: MCP Service on Lambda

**Updated**: 2026-11-03 · **Branch**: `main` · [Spec](spec.md) · [Tasks](tasks.md)

## Scope and status

Provide the existing 39 tools through an isolated ARM64 Lambda entrypoint/image. Preserve original Docker/local/GHCR behavior and locked application dependencies. MCP implements no identity, billing, configuration-store retrieval or workflow logic; its role writes only its own logs.

| Profile | Status and ownership |
|---|---|
| Legacy HTTP API v2 | Delivered `runtime.yaml`; service owns payload-2.0 integration, `ANY /mcp`, `ANY /mcp/`, `GET /health` and alias permissions on supplied `$default` API/authorizer |
| REST API | Planned `runtime-rest.yaml` supplies function/version/live alias/logs/native environment only; spec 002 owns every REST attachment/permission, named stage and native usage plan |

REST uses a distinct endpoint and explicit secured cutover; existing HTTP commands/report v1 do not prove REST readiness. [REST handoff](contracts/rest-migration.md) governs new work. [Spec 002](../../../mcp-auth-subscriptions/specs/002-authentication-api-access/spec.md) owns upstream access/Step Functions; [spec 003](../../../mcp-auth-subscriptions/specs/003-billing-subscriptions/spec.md) owns billing.

## Runtime and packaging

- Python 3.11, existing MCP 1.29.0/Starlette 0.47.2/Uvicorn 0.35.0/HTTPX 0.28.1, uv 0.13.1 and Lambda Web Adapter 1.1.0. Preserve advertised Python 3.10–3.13 support and root production locks.
- Lambda-only `lambda_server.py` validates configuration before importing/reusing the server singleton, enables stateless JSON and SDK session-manager lifespan, then runs one Uvicorn worker on port 8000. Importing this module cannot alter ordinary transports. Test baseline/candidate in separate processes.
- Preserve DNS-rebinding protection; accept configured exact execute-api authority plus internal readiness hosts, reject Origin/forwarded-host reliance and disable proxy-header trust. Local `/mcp/` normalizes without redirect; POST supports finite JSON/notifications, other methods return 405/Allow POST. `/health` returns exact healthy JSON without provider calls or credentials.
- Pin real Python/uv/adapter manifests; install `uv sync --locked --no-dev --no-editable`, disable managed Python downloads and package coinlists. Test the native ARM64 image without mounts, under a non-root user/read-only root with writable `/tmp`. No runtime uv/AWS application SDK.
- Build a single ARM64 image without attestation-index/provenance/SBOM attachments; record source/dirty/lock/config/manifest identities. Build once, test and push the same image. Emulation cannot satisfy native timing gates.

## Configuration and limits

[Data model](data-model.md) owns the complete parameter/default/environment matrix; [deployment contract](contracts/deployment.md) owns lifecycle details.

| Setting | Value/profile |
|---|---|
| Memory / temporary storage / reserved concurrency / log retention | Defaults 1024 MiB / 512 MiB / 5 / 14 days; parameterized |
| Lambda timeout | Default 25 seconds, range 1–25 |
| Gateway integration deadline | Legacy HTTP 30 seconds; planned REST 29 seconds; cold initialization shares the window |
| Client connection / response deadline | 10 / 35 seconds |
| Payload / storage | Respect six-MiB buffered Lambda envelopes including adapter overhead; writable `/tmp` only |
| Adapter | Port 8000, readiness `/health` exactly 200, buffered invocation |

Map all nine `.env.example` settings directly to native Lambda environment variables before startup. Optional provider credentials use NoEcho parameters with empty defaults; supply them through the parameter UI/private file outside checkout/evidence. Validate ranges/literal strings and the combined 4-KB environment limit. Report no credential values/hashes/full environment; NoEcho does not prevent authorized configuration reads. Missing optional values preserve provider fallback. No startup hook/store read/provider call participates in readiness.

## Release and infrastructure

Bootstrap service ECR → ECR-only publishing IAM → immutable image → runtime/version/live alias → gateway attachment → verification. Same account/region, explicit ownership and no Function URL/VPC/NAT/database. Manual native-ARM publication uses protected main/environment OIDC; retain/reuse account providers explicitly and grant no deployment/billing access. Existing GHCR workflow stays independent.

Every code/environment update changes DeploymentRevision and publishes a retained version. Configuration changes need no rebuild. CloudFormation selects alias rollback through RollbackVersion; forward release clears it. Rollback restores the old environment snapshot, so revoked provider credentials require a forward revision using current values. Preserve complete environment inputs during updates. Access policy/subscriptions have separate lifecycles.

Preflight checks artifact/account/region/architecture, exact gateway/authorizer/alias identity, route conflicts, permissions and concurrency capacity. Cleanup removes only owned resources: service owns legacy attachments; access detaches REST wiring first. Preserve supplied access, billing, shared publishing identities and retained release artifacts.

## Verification

- Freeze the pre-feature source SHA/descriptors/launch/publishing expectations in `tests/integration/support/baseline.json` using isolated original source, never candidate-derived expectations. Missing provenance fails explicitly.
- Local checks cover complete paginated catalog, controlled success/errors, invalid input/host/origin/methods, provider-independent health, environment/default/fallback/redaction, native packaging/storage/concurrency/replacement and original Docker/stdio. No production fake-provider flag.
- Live checks prove upstream denial **before MCP invocation**, every attachment/permission and no alternate bypass, resolved release identity and real protocol interactions. Use the deterministic `futures_watchlist` **tool**; `exchanges://list` cannot satisfy a tool call. Report live provider probes separately.
- Require 20 complete initialize/discover/tool interactions, five concurrent clients, two fresh environments joined through gateway/platform IDs to successful same-run/release/target interactions, and ten health checks within five seconds. Health-only/unrelated/failed/uncorrelated starts do not count. Bind sanitized `completed-interactions.json` sidecar evidence.
- `local`, read-only `live` and `combine` preserve compatible release/config/target evidence and all 16 mandatory stages. Missing checks remain not_run; lifecycle walkthrough supplies actual deploy/update/rollback/cleanup evidence. Verifier never provisions/publishes/mutates or directly invokes Lambda as public security proof.
- Keep [report v1](contracts/verification-report.schema.json) byte-identical for HTTP; pending REST schema v2 adds explicit REST provenance without weakening stages/thresholds/privacy/cold joins. REST adapter event/path/multivalue behavior needs packaged tests.

Use the optional deployment test group with lazy AWS imports and separate required Python 3.11 CI; original default unit workflows remain independent. Validate affected tests, IaC, schemas and documentation. Current local-only instruction leaves AWS/host/payment acceptance not_run.

## Evidence and navigation

55 tasks: 42 checked, 13 pending. Earlier 516 passing service tests are historical local evidence; they do not establish REST/access/billing acceptance. Original task/checklist markers and report v1 remain authoritative. The constitution is a template with no enacted additional gate.

[Research](research.md) records legacy design decisions. [Quickstart](quickstart.md), [operator guide](../../docs/lambda-deployment.md), [HTTP contract](contracts/mcp-http.md), [REST handoff](contracts/rest-migration.md) and [history](../scope-migration.md) hold detailed procedures/evidence.
