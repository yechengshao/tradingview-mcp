# MCP implementation rules

Preserve ordinary Docker/stdio transports and frozen tool descriptors/results. Lambda monitoring uses AWS-native CloudWatch Logs/metrics and Lambda/API Gateway X-Ray settings under [spec 001 observability](specs/001-add-lambda-deployment/contracts/observability.md).

Do not add OpenTelemetry, third-party tracing SDKs, custom span exporters, collectors or monitoring workers. Keep request/tool failure timings and correlation IDs in bounded sanitized logs; native AWS manages invocation/service tracing. Never capture arguments/results, URLs/query strings, cookies, keys or raw exception messages. Test redaction/context isolation/native settings; cloud delivery and native image acceptance remain separate from local checks.

AWS resources MUST be created only from CloudFormation templates in `infra/`, never by hand or with ad hoc CLI commands; see the constitution's Infrastructure as Code principle.
