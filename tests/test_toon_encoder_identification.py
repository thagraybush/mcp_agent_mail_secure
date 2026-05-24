"""
Tests for `_looks_like_toon_rust_encoder` (mcp_agent_mail#163).

The function is the gatekeeper for the TOON encoder subprocess: it must
accept the real `toon_rust` binary (currently installed as `toon` from
`cargo install tru`) and reject lookalikes (Node.js toon CLI, coreutils
`tr`, etc.).
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import textwrap
from pathlib import Path

import pytest

# Ensure the in-tree package is importable when running from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_agent_mail import app as app_module  # noqa: E402


def _make_fake_binary(tmp_path: Path, name: str, help_text: str, version_text: str = "") -> str:
    """Build a tiny shell script that prints predictable --help / --version output."""
    script = tmp_path / name
    script.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            case "${{1:-}}" in
              --help) printf '%s\\n' {help_text!r} ;;
              --version) printf '%s\\n' {version_text!r} ;;
              *) printf 'unknown\\n' ; exit 1 ;;
            esac
            """
        )
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    # Reset the function's lru_cache so each scripted scenario is evaluated fresh.
    app_module._looks_like_toon_rust_encoder.cache_clear()
    return str(script)


def test_binary_named_toon_is_accepted_when_banners_identify_toon_rust(tmp_path: Path) -> None:
    """
    `cargo install tru` produces a binary named `toon` (the [[bin]] target's
    name in toon_rust's Cargo.toml). mcp_agent_mail#163: a basename-only
    rejection broke every local install. The post-fix function must
    identify the binary via its help-text banner regardless of basename.
    """
    exe = _make_fake_binary(
        tmp_path,
        name="toon",
        help_text="TOON reference implementation in Rust (JSON <-> TOON)\nusage: toon ...",
    )
    assert app_module._looks_like_toon_rust_encoder(exe) is True


def test_binary_named_tru_is_accepted_via_version_banner(tmp_path: Path) -> None:
    """A binary named `tru` that prints the toon_rust version banner is accepted."""
    exe = _make_fake_binary(
        tmp_path,
        name="tru",
        help_text="usage: tru\n",
        version_text="tru 0.2.3",
    )
    assert app_module._looks_like_toon_rust_encoder(exe) is True


def test_node_js_toon_is_still_rejected(tmp_path: Path) -> None:
    """
    The Node.js toon CLI prints neither the toon_rust help-text marker nor a
    toon_rust version banner, so it must fail identification even though
    it's named `toon`.
    """
    exe = _make_fake_binary(
        tmp_path,
        name="toon",
        help_text="usage: toon [options]\nA JS-based TOON CLI",
        version_text="toon 1.4.2 (node)",
    )
    assert app_module._looks_like_toon_rust_encoder(exe) is False


def test_coreutils_tr_is_rejected(tmp_path: Path) -> None:
    """coreutils `tr` is a real binary on $PATH; it must never be accepted."""
    if not shutil.which("tr"):
        pytest.skip("coreutils tr not available")
    app_module._looks_like_toon_rust_encoder.cache_clear()
    assert app_module._looks_like_toon_rust_encoder("/usr/bin/tr") is False


def test_nonexistent_binary_is_rejected(tmp_path: Path) -> None:
    app_module._looks_like_toon_rust_encoder.cache_clear()
    assert app_module._looks_like_toon_rust_encoder(str(tmp_path / "does-not-exist")) is False
