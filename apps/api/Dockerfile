# API: FastAPI on uvicorn (A4, F1). Build context: the repo root (infra/compose/api.yml).
# In Compose it only enqueues (RUN_DISPATCH=queue), so it carries the gate and the run store but none of
# the agent stack: that lives in the worker image. Multi-arch: python slim and every wheel here ship arm64.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

COPY packages/contracts /src/contracts
COPY packages/observability /src/libs/observability
COPY packages/run_store /src/libs/run_store
COPY packages/gate /src/libs/gate
COPY apps/worker /src/services/worker
COPY apps/api /src/services/api
RUN pip install /src/contracts /src/libs/observability /src/libs/run_store /src/libs/gate \
        /src/services/worker /src/services/api \
    && useradd --create-home --uid 10001 app

USER app
WORKDIR /home/app
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
