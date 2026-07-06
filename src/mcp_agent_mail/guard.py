"""Stub for removed guard module. The pre-commit guard was stripped in the hardening fork."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def install_guard(settings, project_slug: str, repo_path: str) -> Path:
    logger.warning("Pre-commit guard was removed in the hardening fork")
    raise NotImplementedError("Pre-commit guard is not available in the hardened fork")


async def uninstall_guard(repo_path: str) -> bool:
    logger.warning("Pre-commit guard was removed in the hardening fork")
    return False
