# MCP Integration

Brainbox treats MCP as the external tool boundary. The model receives normalized tool metadata and JSON schemas, while the Harness remains responsible for risk, confirmation, execution, and audit events.

## Supported transports

The current adapter supports MCP Streamable HTTP URLs and local stdio servers through the official Python MCP SDK.

## Flow

```text
MCP server
   ↓ list_tools()
MCPToolBridge
   ↓ normalized schemas
ToolRegistry
   ↓ schemas
Needle
   ↓ proposed call
Harness
   ↓ policy / confirmation
MCPToolBridge.call()
   ↓
MCP server
```

Remote MCP tools default to `external` risk. A server can be explicitly configured as read only only when Brainbox's configuration says so. MCP annotations are hints, not a replacement for the local execution policy.

## Safety rules

* Credentials stay outside model context.
* MCP tool schemas are passed to the model, not authentication material.
* Unknown tools are rejected by `ToolRegistry`.
* Remote tools default to confirmation because they can have effects outside the local machine.
* MCP errors are converted into execution failures instead of being treated as successful results.
* Tool input schemas are preserved so the reflex model can produce structured arguments.
