#!/usr/bin/env bash
set -euo pipefail

# Enable comprehensive Rich-based logging
export TOOLS_LOG_ENABLED=true
export LOG_RICH_ENABLED=true
export LOG_LEVEL=DEBUG
export LOG_JSON_ENABLED=false
export HTTP_REQUEST_LOG_ENABLED=true

# Authentication token
export HTTP_BEARER_TOKEN="REDACTED_UPSTREAM_DEV_TOKEN_3"

uv run python -m mcp_agent_mail.cli serve-http "$@"
