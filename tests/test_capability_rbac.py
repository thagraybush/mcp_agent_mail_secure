"""Tests for capability_rbac module (STRATA-215 Phase 2b shadow enforcement)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from mcp_agent_mail.capability_rbac import (
    CapabilityDecision,
    check_and_log,
    check_capability,
    get_agent_capabilities,
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


# ---------------------------------------------------------------------------
# load_matrix
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# resolve_role — name-based + program-based fallback
# ---------------------------------------------------------------------------


class TestResolveRole:
    def test_known_agent_from_matrix(self, matrix_file: Path):
        init(matrix_file)
        assert resolve_role("GentleAnchor") == "backend-engineer"
        assert resolve_role("FuchsiaBridge") == "pm"

    def test_unknown_agent_no_program(self, matrix_file: Path):
        init(matrix_file)
        assert resolve_role("NonexistentAgent") is None

    def test_unknown_agent_with_program_fallback(self, matrix_file: Path):
        init(matrix_file)
        assert resolve_role("RoseStream", program="claude-code") == "backend-engineer"
        assert resolve_role("AmberCompass", program="codex-cli") == "pm"
        assert resolve_role("GoldNanoHarness", program="nano-harness") == "local-inference"

    def test_matrix_name_takes_precedence_over_program(self, matrix_file: Path):
        init(matrix_file)
        assert resolve_role("FuchsiaBridge", program="claude-code") == "pm"

    def test_without_matrix_program_only(self):
        assert resolve_role("AnyAgent", program="governance-supervisor") == "supervisor"

    def test_without_matrix_no_program(self):
        assert resolve_role("AnyAgent") is None

    def test_unknown_program_returns_none(self):
        assert resolve_role("AnyAgent", program="unknown-program") is None


# ---------------------------------------------------------------------------
# check_capability — permit, deny, constraint paths
# ---------------------------------------------------------------------------


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

    def test_program_fallback_in_check(self, matrix_file: Path):
        init(matrix_file)
        decision = check_capability("send_message", "RoseStream", program="claude-code")
        assert decision.allowed is True
        assert decision.role == "backend-engineer"
        assert decision.constraint == "contacts_only"

    def test_send_message_multi_capability(self, matrix_file: Path):
        init(matrix_file)
        decision = check_capability("send_message", "FuchsiaBridge")
        assert decision.allowed is True

    def test_send_message_denied_for_none_role(self, matrix_file: Path):
        init(matrix_file)
        decision = check_capability("register_agent", "WildBay")
        assert decision.allowed is False
        assert decision.role == "local-inference"


# ---------------------------------------------------------------------------
# Shadow vs enforce mode
# ---------------------------------------------------------------------------


class TestShadowMode:
    def test_default_is_shadow(self, matrix_file: Path):
        init(matrix_file)
        assert is_enforcing() is False
        decision = check_capability("register_agent", "GentleAnchor")
        assert decision.shadow is True

    def test_env_var_enables_enforce(self, matrix_file: Path):
        init(matrix_file)
        with mock.patch.dict("os.environ", {"AGENT_MAIL_CAPABILITY_RBAC_ENFORCE": "true"}):
            assert is_enforcing() is True
            decision = check_capability("register_agent", "GentleAnchor")
            assert decision.shadow is False

    def test_matrix_enforcement_mode(self, tmp_path: Path):
        matrix = {**SAMPLE_MATRIX, "enforcement_mode": "enforce"}
        path = tmp_path / "enforcing.json"
        path.write_text(json.dumps(matrix))
        init(path)
        assert is_enforcing() is True


# ---------------------------------------------------------------------------
# Evidence / structured output
# ---------------------------------------------------------------------------


class TestEvidence:
    def test_to_evidence_contains_all_fields(self, matrix_file: Path):
        init(matrix_file)
        decision = check_capability("send_message", "FuchsiaBridge")
        evidence = decision.to_evidence()
        assert evidence["tool_name"] == "send_message"
        assert evidence["agent_name"] == "FuchsiaBridge"
        assert evidence["role"] == "pm"
        assert evidence["allowed"] is True
        assert "timestamp" in evidence
        assert "shadow" in evidence

    def test_denied_evidence_has_reason(self, matrix_file: Path):
        init(matrix_file)
        decision = check_capability("register_agent", "GentleAnchor")
        evidence = decision.to_evidence()
        assert evidence["allowed"] is False
        assert "denied" in evidence["reason"]
        assert evidence["role"] == "backend-engineer"


# ---------------------------------------------------------------------------
# check_and_log (integration of check + logging)
# ---------------------------------------------------------------------------


class TestCheckAndLog:
    def test_logs_allowed(self, matrix_file: Path, caplog):
        init(matrix_file)
        with caplog.at_level("DEBUG"):
            decision = check_and_log("fetch_inbox", "FuchsiaBridge")
        assert decision.allowed is True

    def test_logs_shadow_deny(self, matrix_file: Path, caplog):
        init(matrix_file)
        with caplog.at_level("WARNING"):
            decision = check_and_log("register_agent", "GentleAnchor")
        assert decision.allowed is False
        assert any("SHADOW_DENY" in r.message for r in caplog.records)

    def test_logs_enforce_deny(self, matrix_file: Path, caplog):
        init(matrix_file)
        with mock.patch.dict("os.environ", {"AGENT_MAIL_CAPABILITY_RBAC_ENFORCE": "true"}):
            with caplog.at_level("WARNING"):
                check_and_log("register_agent", "GentleAnchor")
            assert any("DENIED" in r.message and "SHADOW" not in r.message for r in caplog.records)

    def test_logs_constrained(self, matrix_file: Path, caplog):
        init(matrix_file)
        with caplog.at_level("INFO"):
            decision = check_and_log("fetch_inbox", "GentleAnchor")
        assert decision.allowed is True
        assert decision.constraint == "own_only"

    def test_program_fallback_in_check_and_log(self, matrix_file: Path, caplog):
        init(matrix_file)
        with caplog.at_level("DEBUG"):
            decision = check_and_log("send_message", "RoseStream", program="claude-code")
        assert decision.allowed is True
        assert decision.role == "backend-engineer"


# ---------------------------------------------------------------------------
# get_agent_capabilities (whois RBAC extension)
# ---------------------------------------------------------------------------


class TestGetAgentCapabilities:
    def test_returns_capabilities_for_known_agent(self, matrix_file: Path):
        init(matrix_file)
        caps = get_agent_capabilities("FuchsiaBridge")
        assert caps["rbac_loaded"] is True
        assert caps["rbac_role"] == "pm"
        assert caps["rbac_enforcement"] == "shadow"
        assert caps["rbac_capabilities"]["send_messages"] == "allowed"
        assert caps["rbac_capabilities"]["register_agents"] == "denied"

    def test_returns_constrained_capabilities(self, matrix_file: Path):
        init(matrix_file)
        caps = get_agent_capabilities("GentleAnchor")
        assert caps["rbac_capabilities"]["send_messages"] == "constrained:contacts_only"
        assert caps["rbac_capabilities"]["read_inbox"] == "constrained:own_only"

    def test_unknown_agent_without_program(self, matrix_file: Path):
        init(matrix_file)
        caps = get_agent_capabilities("UnknownAgent")
        assert caps["rbac_loaded"] is True
        assert caps["rbac_role"] is None
        assert "not in matrix" in caps["rbac_note"]

    def test_unknown_agent_with_program_fallback(self, matrix_file: Path):
        init(matrix_file)
        caps = get_agent_capabilities("RoseStream", program="claude-code")
        assert caps["rbac_role"] == "backend-engineer"
        assert "rbac_capabilities" in caps

    def test_without_matrix(self):
        caps = get_agent_capabilities("AnyAgent")
        assert caps["rbac_loaded"] is False

    def test_enforce_mode_reflected(self, tmp_path: Path):
        matrix = {**SAMPLE_MATRIX, "enforcement_mode": "enforce"}
        path = tmp_path / "enforcing.json"
        path.write_text(json.dumps(matrix))
        init(path)
        caps = get_agent_capabilities("FuchsiaBridge")
        assert caps["rbac_enforcement"] == "enforce"
