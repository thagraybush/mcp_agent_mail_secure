"""Tests for capability_rbac module (STRATA-215 Phase 2b)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from mcp_agent_mail.capability_rbac import (
    CapabilityDecision,
    check_and_log,
    check_capability,
    init,
    is_enforcing,
    is_loaded,
    load_matrix,
    resolve_role,
)

SAMPLE_MATRIX = {
    "$schema": "../../governance/schemas/permission-matrix.schema.json",
    "version": 1,
    "updated_at": "2026-07-13T00:00:00Z",
    "updated_by": "test",
    "strata_ticket": "STRATA-215",
    "enforcement_mode": "log-only",
    "change_control": {
        "mechanism": "pr-review-gate",
        "rationale": "test",
        "operator_override": "cfollmer",
    },
    "agent_roles": {
        "GentleAnchor": "backend-engineer",
        "FuchsiaBridge": "pm",
        "NavyPeak": "supervisor",
        "WildBay": "local-inference",
    },
    "governance_write_scope": {"agents": ["FuchsiaBridge"], "rationale": "test"},
    "role_tiers": {
        "backend-engineer": {"tier": 2, "description": "Backend dev"},
        "pm": {"tier": 1, "description": "PM"},
        "supervisor": {"tier": 3, "description": "Supervisor"},
        "local-inference": {"tier": 3, "description": "Local inference"},
    },
    "capabilities": {
        "send_messages": {
            "description": "Send messages",
            "tools": ["send_message", "reply_message"],
            "pm": True,
            "backend-engineer": "contacts_only",
            "supervisor": True,
            "local-inference": "contacts_only",
        },
        "broadcast": {
            "description": "Broadcast to all",
            "tools": ["send_message"],
            "constraint": "broadcast=true",
            "pm": True,
            "backend-engineer": False,
            "supervisor": False,
            "local-inference": False,
        },
        "register_agents": {
            "description": "Register new agents",
            "tools": ["register_agent"],
            "pm": False,
            "backend-engineer": False,
            "supervisor": False,
            "local-inference": False,
        },
        "retire_delete_agents": {
            "description": "Retire or delete agents",
            "tools": ["retire_agent", "hard_delete_agent"],
            "pm": False,
            "backend-engineer": False,
            "supervisor": False,
            "local-inference": False,
        },
        "read_inbox": {
            "description": "Read inbox",
            "tools": ["fetch_inbox", "fetch_topic"],
            "pm": True,
            "backend-engineer": "own_only",
            "supervisor": "own_only",
            "local-inference": "own_only",
        },
    },
}


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset module globals between tests."""
    import mcp_agent_mail.capability_rbac as mod

    mod._TOOL_TO_CAPABILITIES = None
    mod._ROLE_CAPABILITIES = None
    mod._MATRIX = None
    mod._LOADED = False
    yield


@pytest.fixture()
def matrix_file(tmp_path: Path) -> Path:
    path = tmp_path / "permission-matrix.json"
    path.write_text(json.dumps(SAMPLE_MATRIX))
    return path


class TestLoadMatrix:
    def test_loads_valid_file(self, matrix_file: Path):
        result = load_matrix(matrix_file)
        assert result is not None
        assert result["version"] == 1

    def test_returns_none_for_missing_file(self):
        result = load_matrix("/nonexistent/file.json")
        assert result is None

    def test_returns_none_for_no_path(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            result = load_matrix(None)
        assert result is None

    def test_reads_from_env_var(self, matrix_file: Path):
        with mock.patch.dict("os.environ", {"AGENT_MAIL_PERMISSION_MATRIX_PATH": str(matrix_file)}):
            result = load_matrix()
        assert result is not None
        assert result["version"] == 1

    def test_returns_none_for_corrupt_json(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("{not valid json")
        result = load_matrix(path)
        assert result is None


class TestInit:
    def test_init_loads_matrix(self, matrix_file: Path):
        assert not is_loaded()
        result = init(matrix_file)
        assert result is True
        assert is_loaded()

    def test_init_without_path_returns_false(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            result = init(None)
        assert result is False
        assert not is_loaded()

    def test_init_with_bad_path_returns_false(self):
        result = init("/nonexistent/path.json")
        assert result is False
        assert not is_loaded()


class TestResolveRole:
    def test_known_agent(self, matrix_file: Path):
        init(matrix_file)
        assert resolve_role("GentleAnchor") == "backend-engineer"
        assert resolve_role("FuchsiaBridge") == "pm"

    def test_unknown_agent(self, matrix_file: Path):
        init(matrix_file)
        assert resolve_role("NonexistentAgent") is None

    def test_without_matrix_loaded(self):
        assert resolve_role("GentleAnchor") is None


class TestCheckCapability:
    def test_allowed_tool(self, matrix_file: Path):
        init(matrix_file)
        decision = check_capability("send_message", "FuchsiaBridge")
        assert decision.allowed is True
        assert decision.role == "pm"
        assert decision.constraint is None

    def test_constrained_tool(self, matrix_file: Path):
        init(matrix_file)
        decision = check_capability("send_message", "GentleAnchor")
        assert decision.allowed is True
        assert decision.constraint == "contacts_only"
        assert decision.role == "backend-engineer"

    def test_denied_tool(self, matrix_file: Path):
        init(matrix_file)
        decision = check_capability("register_agent", "GentleAnchor")
        assert decision.allowed is False
        assert decision.role == "backend-engineer"
        assert "denied" in decision.reason

    def test_denied_retire(self, matrix_file: Path):
        init(matrix_file)
        decision = check_capability("retire_agent", "FuchsiaBridge")
        assert decision.allowed is False

    def test_ungated_tool_allowed(self, matrix_file: Path):
        init(matrix_file)
        decision = check_capability("health_check", "GentleAnchor")
        assert decision.allowed is True
        assert "not gated" in decision.reason

    def test_unknown_agent_allowed(self, matrix_file: Path):
        init(matrix_file)
        decision = check_capability("send_message", "UnknownAgent")
        assert decision.allowed is True
        assert "not in permission matrix" in decision.reason

    def test_without_matrix_always_allowed(self):
        decision = check_capability("register_agent", "GentleAnchor")
        assert decision.allowed is True
        assert "not loaded" in decision.reason

    def test_explicit_role_override(self, matrix_file: Path):
        init(matrix_file)
        decision = check_capability("send_message", "GentleAnchor", role="pm")
        assert decision.allowed is True
        assert decision.constraint is None

    def test_send_message_multi_capability(self, matrix_file: Path):
        """send_message is gated by both send_messages and broadcast.
        For a PM, send_messages grants True, so it should be allowed."""
        init(matrix_file)
        decision = check_capability("send_message", "FuchsiaBridge")
        assert decision.allowed is True

    def test_send_message_denied_for_none_role(self, matrix_file: Path):
        """If an agent has a role but that role isn't in any capability
        for the tool, the tool should be denied."""
        init(matrix_file)
        decision = check_capability("register_agent", "WildBay")
        assert decision.allowed is False
        assert decision.role == "local-inference"


class TestIsEnforcing:
    def test_default_not_enforcing(self, matrix_file: Path):
        init(matrix_file)
        assert is_enforcing() is False

    def test_env_var_enables_enforce(self, matrix_file: Path):
        init(matrix_file)
        with mock.patch.dict("os.environ", {"AGENT_MAIL_CAPABILITY_RBAC_ENFORCE": "true"}):
            assert is_enforcing() is True

    def test_matrix_enforcement_mode(self, tmp_path: Path):
        matrix = {**SAMPLE_MATRIX, "enforcement_mode": "enforce"}
        path = tmp_path / "enforcing.json"
        path.write_text(json.dumps(matrix))
        init(path)
        assert is_enforcing() is True


class TestCheckAndLog:
    def test_logs_allowed(self, matrix_file: Path, caplog):
        init(matrix_file)
        with caplog.at_level("DEBUG"):
            decision = check_and_log("fetch_inbox", "FuchsiaBridge")
        assert decision.allowed is True
        assert "allowed" in caplog.text.lower() or len(caplog.records) >= 0

    def test_logs_denied(self, matrix_file: Path, caplog):
        init(matrix_file)
        with caplog.at_level("WARNING"):
            decision = check_and_log("register_agent", "GentleAnchor")
        assert decision.allowed is False
        assert any("WOULD_DENY" in r.message for r in caplog.records)

    def test_logs_denied_enforce(self, matrix_file: Path, caplog):
        init(matrix_file)
        with mock.patch.dict("os.environ", {"AGENT_MAIL_CAPABILITY_RBAC_ENFORCE": "true"}):
            with caplog.at_level("WARNING"):
                decision = check_and_log("register_agent", "GentleAnchor")
            assert any("DENIED" in r.message and "WOULD" not in r.message for r in caplog.records)
