#!/usr/bin/env bash
# integrate.sh — write MCP server config for coding agents
# Usage: ./scripts/integrate.sh claude|codex|gemini|--all [--dry-run]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

DRY_RUN=0
TARGETS=()

# --- Helpers ---
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
log() { printf '%s\n' "$*"; }

read_token() {
  [[ -f "${ENV_FILE}" ]] || die ".env not found at ${ENV_FILE}. Run install.sh first."
  local token
  token=$(grep -E '^HTTP_BEARER_TOKEN=' "${ENV_FILE}" 2>/dev/null | tail -n 1 | sed 's/^HTTP_BEARER_TOKEN=//') || true
  [[ -n "${token}" ]] || die "HTTP_BEARER_TOKEN not set in ${ENV_FILE}. Run install.sh first."
  printf '%s' "${token}"
}

write_config() {
  local file="$1" content="$2"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "[dry-run] Would write ${file}:"
    log "${content}"
    return 0
  fi
  printf '%s\n' "${content}" > "${file}"
  log "Wrote ${file}"
}

# --- Parse arguments ---
[[ $# -eq 0 ]] && die "Usage: ./scripts/integrate.sh claude|codex|gemini|--all [--dry-run]"

while [[ $# -gt 0 ]]; do
  case "$1" in
    claude)  TARGETS+=("claude") ;;
    codex)   TARGETS+=("codex") ;;
    gemini)  TARGETS+=("gemini") ;;
    --all)   TARGETS=("claude" "codex" "gemini") ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      log "Usage: ./scripts/integrate.sh claude|codex|gemini|--all [--dry-run]"
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

[[ ${#TARGETS[@]} -eq 0 ]] && die "No targets specified. Use claude, codex, gemini, or --all."

# --- Read token from .env (never from other tools' configs) ---
TOKEN=$(read_token)

# --- Build MCP server JSON block ---
mcp_json() {
  local token="$1"
  cat <<EOF
{
  "mcpServers": {
    "agent-mail": {
      "type": "http",
      "url": "http://localhost:8765/mcp",
      "headers": {
        "Authorization": "Bearer ${token}"
      }
    }
  }
}
EOF
}

# --- Write per-target configs ---
for target in "${TARGETS[@]}"; do
  case "${target}" in
    claude)
      write_config "${ROOT_DIR}/.mcp.json" "$(mcp_json "${TOKEN}")"
      ;;
    codex)
      write_config "${ROOT_DIR}/codex.mcp.json" "$(mcp_json "${TOKEN}")"
      ;;
    gemini)
      write_config "${ROOT_DIR}/gemini.mcp.json" "$(mcp_json "${TOKEN}")"
      ;;
  esac
done

log ""
log "Integration complete. Start the server with:"
log "    cd ${ROOT_DIR} && uv run python -m mcp_agent_mail.cli serve-http"
