# Panda Trace Plan Index

## Purpose

This folder breaks Panda Trace into small PRD-style slices so an implementation agent can work section by section without needing to re-decide the product.

Panda Trace is a public, agent-first logs API. It stores, searches, tails, exports, and audits logs for multiple projects and multiple AI agents.

## Read Order

1. [Product Scope](01-product-scope-prd.md)
2. [Platform Stack](02-platform-stack-prd.md)
3. [Public API Contract](03-public-api-contract-prd.md)
4. [Tenancy and Auth](04-tenancy-auth-prd.md)
5. [Log Ingestion](05-log-ingestion-prd.md)
6. [Search, Read, Tail, Export](06-search-read-tail-export-prd.md)
7. [Storage, Indexes, Retention](07-storage-indexes-retention-prd.md)
8. [Security, Abuse Controls, Audit](08-security-abuse-audit-prd.md)
9. [Agent Documentation](09-agent-docs-prd.md)
10. [Implementation Roadmap](10-implementation-roadmap.md)

Also keep [Log Formats](../log-formats.md) nearby. It contains the event schema and Fast App export notes already discussed.

## Locked Direction

- Self-hosted stack only. No paid managed dependency is required.
- API-only product. No human dashboard in v1.
- Agents are users. Treat agents as first-class principals with permissions.
- No raw database queries through the API. Ever.
- Use Postgres for control-plane data and ClickHouse for logs.
- Use OpenAPI plus `llms.txt` style docs so agents can understand the API quickly.

## Implementation Style

Each PRD has:

- Goal
- Locked decisions
- API or data shape
- Acceptance checks
- Space for implementation thinking

The "Think While Implementing" sections are intentionally not fully filled in. Use them to capture local tradeoffs, risks, and discoveries while building.

