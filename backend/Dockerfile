FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TALYN_DATA_DIR=/tmp/talyn
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
RUN useradd --uid 10001 --no-create-home appuser && mkdir -p /tmp/talyn && chown 10001:10001 /tmp/talyn && chmod 1777 /tmp
VOLUME ["/tmp"]
USER 10001
EXPOSE 8000
CMD ["python", "-m", "app.launch", "api"]
