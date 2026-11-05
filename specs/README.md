# MCP Service Specs

This project owns the TradingView MCP service, provider integration, Lambda runtime, service image publication, and publishing IAM.

| Feature | Owns | Status |
| --- | --- | --- |
| [001 — MCP service](001-add-lambda-deployment/spec.md) | Existing tools, finite Lambda transport/health, native provider settings, ECR/publication/IAM | Legacy HTTP delivered locally; existing task completion states preserved; REST/live follow-up pending |

Authentication and subscription specifications now live in the separate [MCP Auth and Subscriptions project](../../mcp-auth-subscriptions/README.md):

- [002 — Authentication and API Access](../../mcp-auth-subscriptions/specs/002-authentication-api-access/spec.md)
- [003 — Billing and Subscriptions](../../mcp-auth-subscriptions/specs/003-billing-subscriptions/spec.md)

The MCP service contains no identity, OAuth, billing, or onboarding implementation and receives no related credentials or permissions. The external project owns access/gateway/authorizer/usage-plan work and billing; this project supplies the service-only integration described in [the REST handoff](001-add-lambda-deployment/contracts/rest-migration.md).

The delivered legacy HTTP profile remains distinct from the planned REST profile. The active service feature remains 001. Existing task/reviewer states and runtime files are unchanged by the project split. [Migration history](scope-migration.md) preserves prior decisions.
