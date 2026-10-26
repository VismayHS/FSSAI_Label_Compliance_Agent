# Stub LLM: OpenAI-compatible stand-in for the provider, for load tests (D6) and the breaker demo (A5).
# Build context: the repo root (infra/compose/stub-llm.yml).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

COPY packages/observability /src/libs/observability
COPY apps/stub_llm /src/services/stub_llm
RUN pip install /src/libs/observability /src/services/stub_llm \
    && useradd --create-home --uid 10001 stub

USER stub
EXPOSE 8080
CMD ["uvicorn", "fssai_stub_llm.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
