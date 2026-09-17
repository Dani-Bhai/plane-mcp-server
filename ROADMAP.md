# Plane MCP Roadmap

This roadmap tracks the work required to turn the current read-only Plane REST adapter into a native, installable, and ergonomic MCP server.

## Current baseline

The current release is `v0.1.0`.

It provides:

- A dependency-free, hand-written JSON-RPC/MCP stdio server.
- Five read-only tools for projects, modules, work items, and comments.
- Environment-based configuration for a self-hosted Plane instance.
- Basic pagination and URL normalization.

The baseline is intentionally preserved while the native implementation is built incrementally.

## Release sequence

| Version | Focus | Status | Depends on |
| --- | --- | --- | --- |
| [`v0.2`](docs/v0.2-native-read-only-foundation.md) | Native MCP foundation and installable read-only server | Complete | `v0.1.0` |
| [`v0.3`](docs/v0.3-native-plane-ux.md) | Native Plane discovery and context UX | Planned | `v0.2` |
| [`v0.4`](docs/v0.4-safe-plane-execution.md) | Safe Plane mutations and execution workflows | Planned | `v0.3` |
| [`v0.5`](docs/v0.5-operational-maturity.md) | Remote transport, security, observability, and maturity | Planned | `v0.4` |

## Implementation order

### 1. Native read-only foundation

Migrate protocol handling to the official MCP Python SDK, preserve the existing five tools, introduce a reusable Plane API client, add an installable command, and establish real protocol/API tests.

### 2. Native Plane UX

Make common reads model-friendly: resolve names to UUIDs, provide project and work-item lookup/search, expose the main Plane metadata objects, and add read-only resources where they improve context loading.

### 3. Safe Plane execution

Add writes only after the read path is typed and tested. Mutations must resolve named objects before writing and read back the changed object to verify the result. Destructive behavior should prefer archive/unarchive and use explicit confirmation boundaries.

### 4. Operational maturity

Add Streamable HTTP, deployment authentication, rate-limit handling, structured diagnostics, release automation, and broader MCP primitives such as prompts or completions where they provide clear value.

## Cross-version principles

- Keep workspace and project boundaries explicit.
- Resolve names to UUIDs before writes; do not duplicate states, labels, types, or other named Plane objects.
- Use PQL for complex filtering, not for mutations.
- Use rich `description_html` when writing Plane descriptions or page content.
- Read back every successful write and verify the expected fields.
- Prefer archive/unarchive over deletion.
- Keep MCP protocol output on stdout and diagnostics on stderr.
- Do not log API keys or other credentials.
- Preserve compatibility with existing tool names unless a breaking change is documented.

## Global definition of done

The project is considered native when it is:

- Implemented on the official MCP SDK rather than hand-written JSON-RPC dispatch.
- Installable and runnable through a stable command without repository-specific paths.
- Usable through standard MCP client flows and the MCP Inspector.
- Backed by unit, protocol, mocked-API, and end-to-end smoke tests.
- Ergonomic enough that common Plane tasks do not require manually finding UUIDs or managing raw cursors.
- Safe for both read and write operations, with explicit annotations and read-back verification.

## Deferred decisions

These decisions should be made during `v0.2` rather than assumed in later versions:

- Whether the first production target is local stdio only or includes Streamable HTTP.
- Which official MCP SDK major/minor version to pin.
- Whether write operations are enabled by default or behind a configuration flag.
- Whether resources and prompts belong in the first native release or the UX release.
- Which Plane API versions and self-hosted Plane releases must be supported.
