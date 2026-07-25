# Phase 3 prep — MCP Python SDK verification

**Date:** 2026-06-11 · **Source:** Context7 `/modelcontextprotocol/python-sdk` (v1.12.4, official, High reputation) · 3 queries.
**Purpose:** Satisfy the #113 Phase-3 gate — *verify the MCP Python SDK API before writing any SDK call shapes* (no shapes from memory). Feeds the Phase-3 implementation plan.

## Verified facts (use these exact shapes in the Phase-3 plan)

### 1. Server + tools — use FastMCP (high-level), not the low-level `Server`
```python
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

mcp = FastMCP("kdb-graph")

@mcp.tool()
def get_entity(slug: str) -> EntityCard:      # docstring becomes the tool description
    """Return node metadata for a slug."""
    ...
```
- `@mcp.tool()` on a **type-hinted** function. Parameter types → the tool's input JSON Schema (validated by the SDK; bad input surfaces as a tool error). The docstring is the description.
- The low-level `Server` (`@server.list_tools()` / `@server.call_tool()` + hand-written `inputSchema`/`outputSchema`) exists but is unnecessary boilerplate for our six thin adapters. **Decision: FastMCP.**

### 2. Structured output — return a Pydantic `BaseModel` per tool
- Returning a `BaseModel` (fields with `Field(description=...)`) auto-generates the tool's **output schema** and `structuredContent`. This is how we deliver the spec's §4.5 requirement ("MCP response shapes are a stable public API — do not return raw in-process dataclasses").
- `TypedDict`, `dict[str, Any]`, and typed plain classes also work. Simple/`list` returns are auto-wrapped as `{"result": ...}`.
- → Define one response model per tool (`EntityCard`, `Neighborhood`, `PathResult`, `BodyResult`, `StressReport`, …) rather than leaking `kdb_graph` dataclasses over the wire.

### 3. Errors — raise; the SDK wraps into `isError=True` + message
- A tool that raises an exception → SDK returns a `CallToolResult` with `isError=True` and the message as `TextContent`; clients check `result.isError`. That IS the error envelope.
- For full control a tool may return `CallToolResult(content=[...], structuredContent=..., _meta=...)` directly.
- → Our domain exceptions (`ContentNotFoundError`, `GraphDBReadOnlyError`, `PathError`) can propagate; optionally wrap each tool to normalize the message. Input-validation errors are handled by the SDK from the type hints.

### 4. Transport — stdio is the default
```python
def main() -> None:
    mcp.run()                 # no arg => stdio

if __name__ == "__main__":
    main()
```
- `mcp.run()` defaults to stdio (HTTP is opt-in: `mcp.run(transport="streamable-http")`). stdio is exactly what we want for the local-first read server (spec F5).

## What this confirms for the Phase-3 design

- **The server is the assembly layer that imports BOTH `kdb_graph` (graph queries/analytics) AND `common.wiki_io.get_body` (content).** Consistent with placement A: `get_body` stays in `common/`; the server joins the two stores. The server is therefore the package's app/transport layer — allowed to depend on `common`, keeping the `kdb_graph` *core* zero-`common`.
- **Per-query reopen (F5):** each tool opens the GraphDB read-only (`read_only=True`, honored since #112), runs its query, returns a Pydantic response, closes — so reads never pin a stale snapshot and never hold a writer-blocking handle. (Mechanics to be specified in the plan: a small context manager around `GraphDB(..., read_only=True)`.)

## Open decisions for the Phase-3 plan (NOT settled here)
- Physical location/name of the server module (package app-layer dir + console-script entry point).
- The `stress_test` composite over `analytics.py` (the Named Gate) — its two new `queries.py` primitives (`indegree`, `entity_list`) and the Pydantic `StressReport` shape.
- Exact Pydantic response model per tool.
- Dependency add: `mcp` (the SDK) as a project/package dependency + `pyproject` wiring.
