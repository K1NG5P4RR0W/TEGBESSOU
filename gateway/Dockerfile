FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml ./
RUN uv sync --no-dev
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
RUN useradd -m appuser && mkdir -p /data/authorizations && chown -R appuser:appuser /app /data
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
