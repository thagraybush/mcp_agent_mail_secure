"""Guard integration tests — skipped in hardened fork (guard module is a stub)."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Pre-commit/pre-push guard removed in hardened fork")


async def test_precommit_no_conflict():
    pass


async def test_precommit_conflict_detected():
    pass
