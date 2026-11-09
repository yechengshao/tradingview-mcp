# Contract: AWS-native MCP CloudWatch and X-Ray

Implements FR-018/SC-009. Use only AWS-native monitoring: CloudWatch Logs/metrics and Lambda/API Gateway X-Ray. No OpenTelemetry, third-party tracing SDK, custom segment/exporter, collector or monitoring worker is introduced. The [shared contract](../../../../mcp-auth-subscriptions/specs/002-authentication-api-access/contracts/observability.md) owns common privacy/cost policy; source/templates are not deployed evidence.

## Application diagnostics

Only the Lambda entrypoint enables stdlib JSON diagnostics. Log startup, unexpected request/tool failures and error envelopes with operation/tool, outcome, duration, opaque correlation/request IDs and available sampled AWS trace/parent IDs. Limit records to 4 KiB and eight safe exception frame locations; capture no messages, source code, locals, arguments/results, credentials, raw URL/query/header/body or provider payloads. Successful health/polling/tool calls do not emit routine INFO volume.

ContextVars isolate concurrent requests and propagate through tool offload threads. Validate incoming x-correlation-id or generate an opaque log reference. Read supported X-Amzn-Trace-Id fields only for diagnosis; never use them as identity or manufacture application trace/span IDs. Return correlation in the response. Lambda Web Adapter is long-running: never infer per-request tracing from its process-wide invocation environment. Actual header propagation needs live verification.

The registered-tool wrapper preserves descriptors/results and emits only sanitized failure timings. Native invocation tracing does not automatically supply tool/Stripe/provider subsegments. Use CloudWatch's safe error/timing records for application detail. Disable raw SDK/Uvicorn logging and guard legacy stdout/stderr prints in Lambda; structured diagnostics retain the original stream. Ordinary Docker/stdio behavior is unchanged.

## AWS configuration

runtime.yaml keeps TracingMode=PassThrough|Active (default PassThrough), ObservabilityEnvironment and configurable LogRetentionDays (legacy default 14; choose 3 in development). Active mode enables Lambda's native X-Ray integration and conditional xray:PutTraceSegments/PutTelemetryRecords permissions (Resource=* required). Log-stream writes stay scoped to the declared group. No app sampling parameter, extra image dependency, custom metric, dashboard or alarm is added by this MCP change.

AWS controls independent Lambda sampling. Spec 002 owns REST stage tracing/native 1% zero-reservoir sampling; the legacy HTTP API has no REST X-Ray integration. Do not promise a 1% rate on every invocation or guaranteed continuous traces across authorizer, webhooks, native calls, queues and redirects. Persist workflow correlation for related logs. T052 must carry native settings into the future service-only REST template; this does not complete REST transport.

## Validation and operations

T056/T057 validate JSON/context/redaction, tool result/error preservation, thread/concurrency isolation, metadata parsing, conditional native IAM, no telemetry dependency and unchanged transports. Search CloudWatch Logs Insights by service=tradingview-mcp and correlation_id within the incident window; use available trace_id to find the native invocation trace and safe stack locations to diagnose failures. Never enable raw payload logging for debugging.

T058 remains pending for native ARM64 image execution and separately authorized real CloudWatch ingestion/retention, Lambda tracing, adapter metadata linkage and effective sampling/overhead. No deployment, image publication or notification is authorized by this contract. Local tests cannot establish live AWS delivery.
