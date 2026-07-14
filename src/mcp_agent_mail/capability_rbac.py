"""STRATA-215 Phase 2b — capability-level RBAC for Agent Mail.

Loads the governance permission matrix and checks whether an agent's role
allows calling a specific MCP tool. Works independently of the existing
reader/writer RBAC in http.py — this module operates at the tool level,
after agent authentication, and covers localhost connections that the
HTTP middleware skips.

Configuration (env vars):
    AGENT_MAIL_PERMISSION_MATRIX_PATH  — path to permission-matrix.json
    AGENT_MAIL_CAPABILITY_RBAC_ENFORCE — "true" to deny, "false"/unset to log-only

When the matrix path is unset, all checks return allowed (fully backward
compatible — no matrix means no capability gating).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TOOL_TO_CAPABILITIES: dict[str, list[str]] | None = None
_ROLE_CAPABILITIES: dict[str, dict[str, Any]] | None = None
_MATRIX: dict[str, Any] | None = None
_LOADED = False


@dataclass(frozen=True)
class CapabilityDecision:
    tool_name: str
    agent_name: str
    role: str
    allowed: bool
    constraint: str | None
    reason: str


def _build_tool_index(matrix: dict[str, Any]) -> dict[str, list[str]]:
    """Map each MCP tool name to the capability(ies) that gate it."""
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
    """Load the permission matrix and build internal indexes. Returns True if loaded."""
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


def resolve_role(agent_name: str) -> str | None:
    """Look up an agent's role from the permission matrix."""
    if _MATRIX is None:
        return None
    return _MATRIX.get("agent_roles", {}).get(agent_name)


def check_capability(
    tool_name: str,
    agent_name: str,
    role: str | None = None,
) -> CapabilityDecision:
    """Check whether an agent's role allows calling a specific MCP tool.

    Returns a CapabilityDecision. When the matrix is not loaded or the tool
    is not gated by any capability, the decision is allowed.
    """
    if not _LOADED or _TOOL_TO_CAPABILITIES is None or _ROLE_CAPABILITIES is None:
        return CapabilityDecision(
            tool_name=tool_name, agent_name=agent_name,
            role=role or "unknown", allowed=True, constraint=None,
            reason="permission matrix not loaded",
        )

    if role is None:
        role = resolve_role(agent_name)
    if role is None:
        return CapabilityDecision(
            tool_name=tool_name, agent_name=agent_name,
            role="unknown", allowed=True, constraint=None,
            reason="agent not in permission matrix",
        )

    cap_names = _TOOL_TO_CAPABILITIES.get(tool_name)
    if not cap_names:
        return CapabilityDecision(
            tool_name=tool_name, agent_name=agent_name,
            role=role, allowed=True, constraint=None,
            reason="tool not gated by any capability",
        )

    for cap_name in cap_names:
        cap = _ROLE_CAPABILITIES.get(cap_name, {})
        perm = cap.get(role)
        if perm is True:
            return CapabilityDecision(
                tool_name=tool_name, agent_name=agent_name,
                role=role, allowed=True, constraint=None,
                reason=f"allowed by capability '{cap_name}'",
            )
        if isinstance(perm, str):
            return CapabilityDecision(
                tool_name=tool_name, agent_name=agent_name,
                role=role, allowed=True, constraint=perm,
                reason=f"allowed with constraint '{perm}' by capability '{cap_name}'",
            )

    denied_by = cap_names[0]
    return CapabilityDecision(
        tool_name=tool_name, agent_name=agent_name,
        role=role, allowed=False, constraint=None,
        reason=f"denied by capability '{denied_by}' (role '{role}' has no permission)",
    )


def log_decision(decision: CapabilityDecision) -> None:
    """Log a capability decision at the appropriate level."""
    if decision.allowed:
        if decision.constraint:
            logger.info(
                "capability_rbac: ALLOWED (constrained) %s → %s [role=%s, constraint=%s] %s",
                decision.agent_name, decision.tool_name, decision.role,
                decision.constraint, decision.reason,
            )
        else:
            logger.debug(
                "capability_rbac: allowed %s → %s [role=%s] %s",
                decision.agent_name, decision.tool_name, decision.role,
                decision.reason,
            )
    else:
        mode = "DENIED" if is_enforcing() else "WOULD_DENY"
        logger.warning(
            "capability_rbac: %s %s → %s [role=%s] %s",
            mode, decision.agent_name, decision.tool_name,
            decision.role, decision.reason,
        )


def check_and_log(
    tool_name: str,
    agent_name: str,
    role: str | None = None,
) -> CapabilityDecision:
    """Check capability and log the decision. Convenience wrapper."""
    decision = check_capability(tool_name, agent_name, role)
    log_decision(decision)
    return decision
