FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system --gid 10001 appgroup \
    && adduser --system --uid 10001 --gid 10001 appuser \
    && mkdir -p /app/output \
    && chown -R appuser:appgroup /app

COPY pyproject.toml README.md /app/
COPY src /app/src

RUN pip install --upgrade pip \
    && pip install -e .

USER appuser

EXPOSE 8777

CMD ["python", "-m", "course_mcp_server.server"]
