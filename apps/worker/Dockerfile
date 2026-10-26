# Worker: `python -m fssai_worker`, the RQ consumer that runs the pipeline (A4, A7). Build context: the repo
# root (infra/compose/worker.yml). It installs every package a pipeline seam can switch to, so flipping an
# IMPL_* variable in .env never needs a different image. Stateless: the index and the embedding model are
# read-only volumes from the indexer, runs go to Postgres, breaker state to Redis. Scale with --scale worker=N.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/data/hf-cache HF_HUB_DISABLE_TELEMETRY=1

# CPU-only torch first, as in packages/ingest/Dockerfile: the default Linux wheel pulls ~2 GB of CUDA libraries.
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN pip install --index-url "${TORCH_INDEX_URL}" "torch>=2.4,<3"

COPY packages/contracts /src/contracts
COPY packages /src/libs
COPY apps/worker /src/services/worker
RUN pip install /src/contracts /src/libs/observability /src/libs/run_store /src/libs/llm_gateway \
        "/src/libs/retrieval[embeddings]" /src/libs/prompts /src/libs/guardrails /src/libs/agents \
        /src/libs/verification /src/services/worker \
    && useradd --create-home --uid 10001 worker

USER worker
WORKDIR /home/worker
EXPOSE 9100
CMD ["python", "-m", "fssai_worker"]
