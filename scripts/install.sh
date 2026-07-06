#!/usr/bin/env bash
# install.sh — minimal installer for mcp_agent_mail_secure
# Usage: ./scripts/install.sh [--dir <path>] [--quiet] [--dry-run]
set -euo pipefail

REPO_URL="https://github.com/thagraybush/mcp_agent_mail_secure.git"
DEFAULT_DIR="${HOME}/.local/share/mcp_agent_mail_secure"

# --- Defaults ---
INSTALL_DIR=""
QUIET=0
DRY_RUN=0

# --- Helpers ---
log()  { [[ "$QUIET" -eq 1 ]] && return 0; printf '%s\n' "$*"; }
err()  { printf 'ERROR: %s\n' "$*" >&2; }
die()  { err "$@"; exit 1; }

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      shift
      [[ $# -eq 0 ]] && die "--dir requires a path argument"
      INSTALL_DIR="$1"
      ;;
    --dir=*)
      INSTALL_DIR="${1#*=}"
      ;;
    --quiet)
      QUIET=1
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help)
      cat <<EOF
Usage: ./scripts/install.sh [OPTIONS]

Options:
  --dir <path>   Install location (default: ${DEFAULT_DIR})
  --quiet        Minimal output
  --dry-run      Print what would be done without modifying anything
  -h, --help     Show this help
EOF
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
  shift
done

INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_DIR}"

# --- Preflight checks ---

# Require uv (do NOT auto-install it)
if ! command -v uv >/dev/null 2>&1; then
  die "uv is required but not found. Install it first: https://docs.astral.sh/uv/getting-started/installation/"
fi

# Require git
if ! command -v git >/dev/null 2>&1; then
  die "git is required but not found."
fi

# Require python3 or openssl for token generation
if ! command -v python3 >/dev/null 2>&1 && ! command -v openssl >/dev/null 2>&1; then
  die "python3 or openssl is required for secure token generation."
fi

# --- Dry-run mode ---
run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "[dry-run] $*"
    return 0
  fi
  "$@"
}

# --- Step 1: Clone or reuse existing checkout ---
log "==> Install directory: ${INSTALL_DIR}"

if [[ -d "${INSTALL_DIR}/.git" ]]; then
  log "    Using existing checkout at ${INSTALL_DIR}"
elif [[ -d "${INSTALL_DIR}" ]] && [[ "$(ls -A "${INSTALL_DIR}" 2>/dev/null)" ]]; then
  die "Directory ${INSTALL_DIR} exists and is not empty (and not a git repo). Remove it or choose another --dir."
else
  log "    Cloning ${REPO_URL} ..."
  run git clone --depth 1 "${REPO_URL}" "${INSTALL_DIR}"
fi

# --- Step 2: Install dependencies via uv ---
log "==> Installing dependencies ..."
run uv sync --project "${INSTALL_DIR}"

# --- Step 3: Generate bearer token and write .env ---
ENV_FILE="${INSTALL_DIR}/.env"

if [[ -f "${ENV_FILE}" ]]; then
  log "    .env already exists at ${ENV_FILE} -- skipping token generation"
else
  log "==> Generating bearer token ..."
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "[dry-run] generate token and write to ${ENV_FILE}"
  else
    TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    printf 'HTTP_BEARER_TOKEN=%s\n' "${TOKEN}" > "${ENV_FILE}"
    chmod 600 "${ENV_FILE}"
    log "    Token written to ${ENV_FILE} (permissions: 600)"
  fi
fi

# --- Done ---
log ""
log "==> Installation complete."
log ""
log "To start the server:"
log "    cd ${INSTALL_DIR}"
log "    uv run python -m mcp_agent_mail.cli serve-http"
log ""
log "To integrate with Claude Code, add to your project's .mcp.json:"
log '    {'
log '      "mcpServers": {'
log '        "agent-mail": {'
log '          "type": "http",'
log '          "url": "http://localhost:8765/mcp",'
log '          "headers": {'
log '            "Authorization": "Bearer <token-from-.env>"'
log '          }'
log '        }'
log '      }'
log '    }'
log ""
log "For automated integration, run: ./scripts/integrate.sh claude"
