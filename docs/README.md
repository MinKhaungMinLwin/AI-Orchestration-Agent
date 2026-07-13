# T-Station AI Documentation

This directory contains documentation for the current Chat V3 runtime and its supporting services.

## Start Here

- [Chat V3 migration and runtime guide](chat-v3/MIGRATE_V2_TO_V3_EN.md) — controlling guide for runtime work
- [System architecture](system-architecture.md) — current service and Chat V3 architecture
- [Codebase summary](codebase-summary.md) — repository layout and component ownership
- [Code standards](code-standards.md) — implementation conventions

## Architecture

- [Full architecture diagrams](full-architecture-mermaid.md) — Mermaid system and request-flow diagrams

The diagrams in this section describe Chat V3. Older V2 coordinator and agent-chain diagrams were removed because they
no longer represent the active runtime.

## Operations and Evaluation

- [Langfuse monitoring guide](operations/langfuse-monitoring-guide.md)
- [Support FAQ hybrid-search benchmark](eval/support-agent-faq-hybrid-benchmark.md)

## Security

- [Docker security requirements](docker-sec/requirements.md)
- [Docker security implementation summary](docker-sec/after.md)
- [Docker security baseline report](docker-sec/before.md)
- [Docker image scan guide](docker-sec/guide-scan.md)

## Documentation Policy

- Document the active Chat V3 structure, not planned or superseded V2 architecture.
- Keep completed migration plans and detailed change history in Git history and `FIX_LOG.md` instead of `docs/`.
- Update architecture documents in the same change as runtime ownership or data-flow changes.
- Do not add generated repository dumps or duplicate translations to this directory.
