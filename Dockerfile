# ── Builder: install dependencies ─────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Pre-compile bytecode so the runtime image starts faster.
# Copy mode makes the .venv fully self-contained (no symlinks to uv cache).
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install dependencies first — this layer is cached unless pyproject.toml or uv.lock changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source and register the project entry point
COPY . .
RUN uv sync --frozen --no-dev

# Pre-download the FastEmbed model into /app so it's copied to the runtime stage
ENV FASTEMBED_CACHE_PATH=/app/.fastembed_cache
RUN /app/.venv/bin/python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

# ── Runtime: lean image without uv ────────────────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# Copy the pre-built virtual environment and source from the builder
COPY --from=builder /app /app

# Put the venv on PATH so `python` resolves to the venv interpreter
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV FASTEMBED_CACHE_PATH=/app/.fastembed_cache

EXPOSE 8000 8001

CMD ["python", "main.py"]
