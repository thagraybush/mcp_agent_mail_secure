"""Guard pre-push tests — skipped in hardened fork (guard module is a stub)."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Pre-commit/pre-push guard removed in hardened fork")


def test_prepush_blocks_on_conflict_with_real_range() -> None:
    pass


def test_prepush_warns_on_conflict_in_warn_mode() -> None:
    pass


def test_prepush_fallback_matches_backslash_pattern() -> None:
    pass
