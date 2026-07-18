"""STRATA-215 Phase 2b — capability-level RBAC for Agent Mail.

Loads the governance permission matrix and checks whether an agent's role
allows calling a specific MCP tool. Works independently of the existing
reader/writer RBAC in http.py — this module operates at the tool level,
after agent authentication, and covers localhost connections that the
HTTP middleware skips.

Configuration (env vars):
    AGENT_MAIL_PERMISSION_MATRIX_PATH  — path to permission-matrix.json
    AGENT_MAIL_CAPABILITY_RBAC_ENFORCE — "true" to deny, "false"/unset to log-only (shadow)

When the matrix path is unset, all checks return allowed (fully backward
compatible — no matrix means no capability gating).

Shadow mode produces structured decision evidence on every tool call,
suitable for operator review before switching to enforce mode.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TOOL_TO_CAPABILITIES: dict[str, list[str]] | None = None
_ROLE_CAPABILITIES: dict[str, dict[str, Any]] | None = None
_MATRIX: dict[str, Any] | None = None
_LOADED = False

PROGRAM_ROLE_DEFAULTS: dict[str, str] = {
    "claude-code": "backend-engineer",
    "codex-cli": "pm",
    "antigravity": "backend-engineer",
    "governance-supervisor": "supervisor",
    "nano-harness": "local-inference",
}


@dataclass(frozen=True)
class CapabilityDecision:
    tool_name: str
    agent_name: str
    role: str
    allowed: bool
    constraint: str | None
    reason: str
    shadow: bool = True
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_evidence(self) -> dict[str, Any]:
        return asdict(self)


def _build_tool_index(matrix: dict[str, Any]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for cap_name, cap in matrix.get("capabilities", {}).items():
        for tool in cap.get("tools", []):
            index.setdefault(tool, []).append(cap_name)
    return index


def load_matrix(path: str | Path | None = None) -> dict[str, Any] | None:
    if path is None:
        path = os.environ.get("AGENT_MAIL_PERMISSION_MATRIX_PATH")
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        logger.warning("capability_rbac: cannot load permission matrix at %s: %s", path, exc)
        return None


def init(matrix_path: str | Path | None = None) -> bool:
    global _TOOL_TO_CAPABILITIES, _ROLE_CAPABILITIES, _MATRIX, _LOADED
    matrix = load_matrix(matrix_path)
    if matrix is None:
        _LOADED = False
        return False
    _MATRIX = matrix
    _TOOL_TO_CAPABILITIES = _build_tool_index(matrix)
    _ROLE_CAPABILITIES = matrix.get("capabilities", {})
    _LOADED = True
    agent_count = len(matrix.get("agent_roles", {}))
    cap_count = len(_ROLE_CAPABILITIES)
    logger.info(
        "capability_rbac: loaded permission matrix v%s (%d agents, %d capabilities, mode=%s)",
        matrix.get("version", "?"), agent_count, cap_count,
        matrix.get("enforcement_mode", "unknown"),
    )
    return True


def is_loaded() -> bool:
    return _LOADED


def is_enforcing() -> bool:
    env = os.environ.get("AGENT_MAIL_CAPABILITY_RBAC_ENFORCE", "").lower()
    if env == "true":
        return True
    return bool(_MATRIX and _MATRIX.get("enforcement_mode") == "enforce")


def resolve_role(
    agent_name: str,
    program: str | None = None,
) -> str | None:
    """Resolve an agent's role.

    Resolution order:
    1. Explicit agent_roles mapping in the permission matrix
    2. Program-based default (e.g. codex-cli → pm)
    3. None (unknown)
    """
    if _MATRIX is not None:
        role = _MATRIX.get("agent_roles", {}).get(agent_name)
        if role is not None:
            return role
    if program is not None:
        return PROGRAM_ROLE_DEFAULTS.get(program)
    return None


def check_capability(
    tool_name: str,
    agent_name: str,
    role: str | None = None,
    program: str | None = None,
) -> CapabilityDecision:
    enforcing = is_enforcing()

    if not _LOADED or _TOOL_TO_CAPABILITIES is None or _ROLE_CAPABILITIES is None:
        return CapabilityDecision(
            tool_name=tool_name, agent_name=agent_name,
            role=role or "unknown", allowed=True, constraint=None,
            reason="permission matrix not loaded",
            shadow=not enforcing,
        )

    if role is None:
        role = resolve_role(agent_name, program)
    if role is None:
        return CapabilityDecision(
            tool_name=tool_name, agent_name=agent_name,
            role="unknown", allowed=True, constraint=None,
            reason="agent not in permission matrix and no program default",
            shadow=not enforcing,
        )

    cap_names = _TOOL_TO_CAPABILITIES.get(tool_name)
    if not cap_names:
        return CapabilityDecision(
            tool_name=tool_name, agent_name=agent_name,
            role=role, allowed=True, constraint=None,
            reason="tool not gated by any capability",
            shadow=not enforcing,
        )

    for cap_name in cap_names:
        cap = _ROLE_CAPABILITIES.get(cap_name, {})
        perm = cap.get(role)
        if perm is True:
            return CapabilityDecision(
                tool_name=tool_name, agent_name=agent_name,
                role=role, allowed=True, constraint=None,
                reason=f"allowed by capability '{cap_name}'",
                shadow=not enforcing,
            )
        if isinstance(perm, str):
            return CapabilityDecision(
                tool_name=tool_name, agent_name=agent_name,
                role=role, allowed=True, constraint=perm,
                reason=f"allowed with constraint '{perm}' by capability '{cap_name}'",
                shadow=not enforcing,
            )

    denied_by = cap_names[0]
    return CapabilityDecision(
        tool_name=tool_name, agent_name=agent_name,
        role=role, allowed=False, constraint=None,
        reason=f"denied by capability '{denied_by}' (role '{role}' has no permission)",
        shadow=not enforcing,
    )


def log_decision(decision: CapabilityDecision) -> None:
    evidence = decision.to_evidence()
    if decision.allowed:
        if decision.constraint:
            logger.info(
                "capability_rbac: ALLOWED (constrained) %s → %s [role=%s, constraint=%s] %s",
                decision.agent_name, decision.tool_name, decision.role,
                decision.constraint, decision.reason,
                extra={"rbac_evidence": evidence},
            )
        else:
            logger.debug(
                "capability_rbac: allowed %s → %s [role=%s] %s",
                decision.agent_name, decision.tool_name, decision.role,
                decision.reason,
                extra={"rbac_evidence": evidence},
            )
    else:
        mode = "DENIED" if is_enforcing() else "SHADOW_DENY"
        logger.warning(
            "capability_rbac: %s %s → %s [role=%s] %s",
            mode, decision.agent_name, decision.tool_name,
            decision.role, decision.reason,
            extra={"rbac_evidence": evidence},
        )


def check_and_log(
    tool_name: str,
    agent_name: str,
    role: str | None = None,
    program: str | None = None,
) -> CapabilityDecision:
    decision = check_capability(tool_name, agent_name, role, program)
    log_decision(decision)
    return decision


def get_agent_capabilities(
    agent_name: str,
    role: str | None = None,
    program: str | None = None,
) -> dict[str, Any]:
    """Return a summary of an agent's RBAC posture for whois."""
    if not _LOADED or _ROLE_CAPABILITIES is None:
        return {"rbac_loaded": False}
    if role is None:
        role = resolve_role(agent_name, program)
    if role is None:
        return {"rbac_loaded": True, "rbac_role": None, "rbac_note": "agent not in matrix"}

    caps: dict[str, Any] = {}
    for cap_name, cap in _ROLE_CAPABILITIES.items():
        perm = cap.get(role)
        if perm is True:
            caps[cap_name] = "allowed"
        elif isinstance(perm, str):
            caps[cap_name] = f"constrained:{perm}"
        elif perm is False:
            caps[cap_name] = "denied"
        else:
            caps[cap_name] = "no_entry"

    return {
        "rbac_loaded": True,
        "rbac_role": role,
        "rbac_enforcement": "enforce" if is_enforcing() else "shadow",
        "rbac_capabilities": caps,
    }
