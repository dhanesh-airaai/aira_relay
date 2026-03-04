FROM python:3.13-slim

WORKDIR /app

# Copy uv from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Copy everything first so uv can install the project + its script entry point
COPY . .

# Install dependencies and register the aira-relay script
RUN uv sync --frozen --no-dev

EXPOSE 8000 8001

ENV MCP_TRANSPORT=http

ENTRYPOINT ["uv", "run", "python", "main.py"]
