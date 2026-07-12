"""Guard rename tests — skipped in hardened fork (guard module is a stub)."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Pre-commit/pre-push guard removed in hardened fork")


def test_precommit_blocks_on_rename_conflict() -> None:
    pass


def test_precommit_warns_on_rename_conflict_in_warn_mode() -> None:
    pass
