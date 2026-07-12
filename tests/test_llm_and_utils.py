from __future__ import annotations

import pytest

from mcp_agent_mail.llm import complete_system_user
from mcp_agent_mail.utils import generate_agent_name, sanitize_agent_name, slugify


def test_llm_stub_module_has_complete_system_user():
    """LLM module stub exposes complete_system_user (returns None in hardened fork)."""
    assert callable(complete_system_user)


def test_utils_functions_basic():
    assert slugify(" My Project ") == "my-project"
    assert sanitize_agent_name(" A!@#gent 123 ") == "Agent123"
    assert sanitize_agent_name(" Blue-Lake! ") == "BlueLake"
    assert sanitize_agent_name("@@@") is None
    name = generate_agent_name()
    assert isinstance(name, str) and len(name) > 0


@pytest.mark.asyncio
async def test_complete_system_user_returns_none_in_hardened_fork():
    """In the hardened fork, complete_system_user always returns None."""
    out = await complete_system_user("sys", "user")
    assert out is None

