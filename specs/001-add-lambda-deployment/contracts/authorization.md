# Authorization Ownership Moved to Spec 002

The authoritative [authorization contract](../../../../mcp-auth-subscriptions/specs/002-authentication-api-access/contracts/authorization.md) now belongs to spec 002. Human sign-in with PKCE is user-confirmed; the authorizer enforces subscriptions using spec 003 entitlement data. This service feature consumes only the protected gateway interface and implements no identity or billing logic. This forwarding document preserves existing links; it does not define a second authorizer implementation.
