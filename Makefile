# Thin wrappers. Every target is one command you can also type by hand (Windows has no make): the command
# is printed next to each target below and in the README.
PYTHON ?= python3

.PHONY: help env up down logs ps smoke test audit demo-breaker clean-clone cost report

help:            ## list the targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/'

env:             ## create .env from .env.example if missing        (cp .env.example .env)
	@test -f .env || cp .env.example .env

up: env          ## build and start the whole stack                  (docker compose up -d --build)
	docker compose up -d --build

down:            ## stop it, keep the data                            (docker compose down)
	docker compose down

logs:            ## follow the logs                                   (docker compose logs -f --tail=100)
	docker compose logs -f --tail=100

ps:              ## service status and health                         (docker compose ps)
	docker compose ps

smoke:           ## the stack serves a valid request (demo #1)        (python scripts/smoke.py)
	$(PYTHON) scripts/smoke.py

test:            ## every package's tests                             (python scripts/test_all.py)
	$(PYTHON) scripts/test_all.py

audit:           ## no keys, endpoints or model ids in the repo (D4)  (python scripts/audit_secrets.py)
	$(PYTHON) scripts/audit_secrets.py

demo-breaker:    ## circuit breaker opens and recovers (demo #8)      (docker compose exec worker python -m fssai_llm_gateway.demo)
	docker compose exec worker python -m fssai_llm_gateway.demo

clean-clone:     ## fresh clone -> compose up -> smoke (demo #1)      (python scripts/clean_clone_test.py)
	$(PYTHON) scripts/clean_clone_test.py

cost:            ## cost per 100 runs and the biggest driver (L5)     (python scripts/cost_report.py)
	$(PYTHON) scripts/cost_report.py

report:          ## assemble docs/report/REPORT.md from every section (S4.3) (python scripts/build_report.py)
	$(PYTHON) scripts/build_report.py
