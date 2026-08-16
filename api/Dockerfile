FROM python:3.12-slim AS base

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv/api

# System deps: curl for healthcheck, build tools left out (pure Python deps).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        curl \
 && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY api /srv/api

# Run as non-root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
