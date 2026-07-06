"""Stub for removed LLM module. LLM features (summarization, AI suggestions) were stripped in the hardening fork."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def complete_system_user(
    system: str,
    user: str,
    max_tokens: int = 400,
    model: Optional[str] = None,
) -> Optional[str]:
    logger.debug("LLM completion skipped (hardened fork — LLM module removed)")
    return None
