# syntax=docker/dockerfile:1.7

# --------------------------------------------------------------------------
# Stage 1: build the toon_rust encoder (`tru`).
#
# The Python runtime can shell out to a `tru` binary to encode payloads in
# TOON format (`format='toon'` on any tool call). Without `tru` on $PATH the
# code path silently falls back to JSON. The image used to ship without a
# TOON encoder at all, so every `format='toon'` request from a container
# deployment was silently downgraded — see issue #163.
#
# We build the encoder from source pinned to a specific ref (default: main)
# so the container's TOON output matches a known toon_rust commit, then copy
# the single binary into the runtime stage. The crate name on cargo install
# is `tru` but the [[bin]] target name is `toon`, so we rename on copy.
# (Renaming the target upstream is tracked separately; this Dockerfile is
# tolerant of either name today.)
# --------------------------------------------------------------------------
#
# toon_rust pins nightly via rust-toolchain.toml. Install rustup into a
# stable Debian base, let the toolchain file drive channel selection — that
# way this builder stage tracks whatever toon_rust pins without us having
# to bump a hard-coded image tag every nightly cycle.
FROM debian:bookworm-slim AS tru-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential git ca-certificates pkg-config && \
    rm -rf /var/lib/apt/lists/*

# Install rustup with a minimal profile; the project's rust-toolchain.toml
# will pull the right channel + components on first `cargo` invocation.
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain none --profile minimal --no-modify-path

ARG TOON_RUST_REPO=https://github.com/Dicklesworthstone/toon_rust.git
ARG TOON_RUST_REF=main

RUN git clone --depth 1 --branch "${TOON_RUST_REF}" "${TOON_RUST_REPO}" /build/toon_rust && \
    cd /build/toon_rust && \
    cargo build --release && \
    # The [[bin]] target is currently named "toon" but mcp_agent_mail expects
    # the binary on $PATH as `tru`. Copy under the expected name. Fall back
    # to whichever target file exists so this stage stays valid if/when the
    # upstream [[bin]] target is renamed to `tru`.
    install -m 0755 \
        "$(test -f target/release/toon && echo target/release/toon || echo target/release/tru)" \
        /tru && \
    strip /tru

# --------------------------------------------------------------------------
# Stage 2: Python application runtime.
# --------------------------------------------------------------------------
FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    PYTHONPATH=/app/src

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install uv to a shared path so it remains available after USER switch
RUN curl -LsSf https://astral.sh/uv/install.sh | UV_UNMANAGED_INSTALL=/usr/local/bin sh

# Install the TOON encoder built in stage 1 so `format='toon'` requests are
# served by the real toon_rust encoder rather than silently falling back to
# JSON. /usr/local/bin is on $PATH for all users including the unprivileged
# appuser below.
COPY --from=tru-builder /tru /usr/local/bin/tru

WORKDIR /app

# Copy project metadata and sync deps first for better caching
# README.md is required by hatchling since pyproject.toml references it
COPY pyproject.toml README.md ./
# Install runtime deps
RUN uv sync --no-dev

# Copy source
COPY src ./src

# Defaults suitable for container
ENV HTTP_HOST=0.0.0.0 \
    STORAGE_ROOT=/data/mailbox

EXPOSE 8765
VOLUME ["/data"]

# Create non-root user and set ownership on data dir
RUN adduser --disabled-password --gecos "" --uid 10001 appuser && \
    mkdir -p /data/mailbox && chown -R appuser:appuser /data /app
USER appuser

# Mark the mounted mailbox directory as a git safe.directory so git does not
# refuse to operate when the host volume is owned by a different uid than
# appuser (uid 10001) — a common Docker-on-Linux scenario. Without this, git
# treats /data/mailbox (and every per-project repo created underneath it) as
# "dubious ownership" and falls back to a compat mode that fails with
# "Unknown parameter: --cached" on diff/status operations.
#
# git safe.directory entries must be absolute paths (no glob patterns other
# than the special catch-all '*'). Since per-project repos live at
# /data/mailbox/<slug>, we need the catch-all to cover the container's
# dynamically-created subdirectories. This is safe here because the user has
# explicitly mounted the volume into this dedicated container.
# See: https://github.com/Dicklesworthstone/mcp_agent_mail/issues/143
RUN git config --global --add safe.directory /data/mailbox && \
    git config --global --add safe.directory '*'

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8765/health/liveness || exit 1

# Run the HTTP server via the prebuilt venv (avoids uv overhead at startup)
CMD ["/app/.venv/bin/python", "-m", "mcp_agent_mail.cli", "serve-http"]
