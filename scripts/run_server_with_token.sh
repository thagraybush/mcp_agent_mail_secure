#!/usr/bin/env bash
set -euo pipefail
export HTTP_BEARER_TOKEN="REDACTED_UPSTREAM_DEV_TOKEN_5"
uv run python -m mcp_agent_mail.cli serve-http "$@"
