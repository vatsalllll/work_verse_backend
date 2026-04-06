FROM python:3.11-slim

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the working directory.
WORKDIR /app

# Install the application dependencies.
COPY uv.lock pyproject.toml README.md ./
RUN uv sync --frozen --no-cache

# Copy the application into the container.
COPY src/philoagents philoagents/
COPY tools tools/

ENV PORT=8000
EXPOSE ${PORT}
CMD /app/.venv/bin/fastapi run philoagents/infrastructure/api.py --port ${PORT} --host 0.0.0.0
