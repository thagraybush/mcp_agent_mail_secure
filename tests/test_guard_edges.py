"""Guard edge-case tests — skipped in hardened fork (guard module is a stub)."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Pre-commit/pre-push guard removed in hardened fork")


async def test_guard_render_and_conflict_message():
    pass


async def test_uninstall_guard_removes_agent_mail_windows_shims():
    pass

