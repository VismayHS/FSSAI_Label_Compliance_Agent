# Live quality scorer (owner Vihaan; L6): python -m fssai_eval live --every N, scoring recent runs into
# quality_scores. Built from the repo root: deploy/compose/eval-scorer.yml.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# EVAL_EXTRAS=trulens adds the TruLens judge (--judge trulens); the default image scores offline.
ARG EVAL_EXTRAS=""
COPY contracts /src/contracts
COPY libs/observability /src/libs/observability
COPY libs/run_store /src/libs/run_store
COPY libs/llm_gateway /src/libs/llm_gateway
COPY libs/gate /src/libs/gate
COPY libs/verification /src/libs/verification
COPY eval /src/eval
RUN pip install /src/contracts /src/libs/observability /src/libs/run_store /src/libs/llm_gateway /src/libs/gate \
        /src/libs/verification "/src/eval${EVAL_EXTRAS:+[$EVAL_EXTRAS]}" \
    && useradd --create-home --uid 10001 scorer

USER scorer
WORKDIR /home/scorer
CMD ["sh", "-c", "python -m fssai_eval --env-file '' live --every ${LIVE_SCORE_EVERY_S:-300}"]
