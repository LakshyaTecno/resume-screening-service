# syntax=docker/dockerfile:1

FROM python:3.11-slim AS builder
WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .


FROM python:3.11-slim AS runtime
WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home /app app

COPY --from=builder /opt/venv /opt/venv
COPY app ./app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app
EXPOSE 8000

# Overridden with `python -m app.worker` for the worker deployment (see the Helm chart).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
