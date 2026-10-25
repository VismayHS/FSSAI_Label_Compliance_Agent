# Indexer: one-shot job that builds the regulation index into the index-data volume (D2, N2.3).
# Build context: the repo root (deploy/compose/indexer.yml). Multi-arch: python slim and the CPU torch
# wheels exist for amd64 and arm64, so this builds on Windows/WSL and Apple Silicon alike.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/data/hf-cache HF_HUB_DISABLE_TELEMETRY=1

# CPU-only torch first: the default wheel on Linux pulls ~2 GB of CUDA libraries we never use.
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN pip install --index-url "${TORCH_INDEX_URL}" "torch>=2.4,<3"

COPY contracts /src/contracts
COPY libs/observability /src/libs/observability
COPY libs/retrieval /src/libs/retrieval
COPY libs/ingest /src/libs/ingest
RUN pip install /src/contracts /src/libs/observability "/src/libs/retrieval[embeddings]" /src/libs/ingest \
    && useradd --create-home --uid 10001 indexer \
    && mkdir -p /data/index /data/hf-cache && chown -R indexer /data

USER indexer
WORKDIR /home/indexer
# Idempotent: with an unchanged corpus this exits 0 in seconds and rewrites nothing.
CMD ["python", "-m", "fssai_ingest", "build", "--corpus", "/corpus/raw", "--out", "/data/index", "--reembed", "changed"]
