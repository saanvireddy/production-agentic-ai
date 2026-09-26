# Common tasks. `make help` lists them.
PY ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

.DEFAULT_GOAL := help
.PHONY: help venv lint fmt test test-integration eval-retrieval eval-sql eval-ragas up up-ollama down logs \
        load-test ui k8s-up k8s-down helm-lint tf-plan clean

help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

venv: ## Create the virtualenv and install dev dependencies
	$(PY) -m venv $(VENV) && $(BIN)/pip install -U pip && $(BIN)/pip install -r requirements-dev.txt

lint: ## Ruff lint + format check
	$(BIN)/ruff check . && $(BIN)/ruff format --check .

fmt: ## Auto-format
	$(BIN)/ruff check . --fix && $(BIN)/ruff format .

test: ## Unit tests + evaluation gates (no services needed)
	$(BIN)/pytest -q

test-integration: ## Integration tests (needs `docker compose up -d postgres redis`)
	LLM_PROVIDER=fake EMBEDDING_PROVIDER=hash RETRIEVAL_MIN_SCORE=0.1 $(BIN)/pytest -m integration -q

eval-retrieval: ## Retrieval hit-rate / MRR against pgvector (runs inside the api container)
	mkdir -p reports
	docker compose exec api python -m app.evaluation.retrieval --out /tmp/retrieval_eval.json
	docker compose cp api:/tmp/retrieval_eval.json reports/retrieval_eval.json

eval-sql: ## Text-to-SQL execution accuracy with the configured LLM (inside the api container)
	mkdir -p reports
	docker compose exec api python -m app.evaluation.sql_eval --out /tmp/sql_eval.json
	docker compose cp api:/tmp/sql_eval.json reports/sql_eval.json

JUDGE ?= llama3.1:8b
eval-ragas: ## Ragas LLM-as-judge evaluation against the running API (separate venv on the host)
	test -d .venv-eval || ($(PY) -m venv .venv-eval && .venv-eval/bin/pip install -r requirements-eval.txt)
	RAGAS_DO_NOT_TRACK=true .venv-eval/bin/python -m app.evaluation.ragas_eval --judge-model $(JUDGE) \
	  --password "$$(grep -E '^ADMIN_PASSWORD=' .env | cut -d= -f2-)"

up: ## Start the full stack with Docker Compose (Ollama on the host)
	docker compose up -d --build

up-ollama: ## Start the full stack with Ollama in a container
	docker compose --profile ollama up -d --build

down: ## Stop the stack
	docker compose --profile ollama down

logs: ## Tail API logs
	docker compose logs -f api

load-test: ## Locust: 10 / 50 / 100 users, 2 min each -> reports/
	mkdir -p reports
	for u in 10 50 100; do $(BIN)/locust -f scripts/locustfile.py --host http://localhost:8000 --headless \
	  -u $$u -r 10 -t 2m --csv reports/load_$${u}u --html reports/load_$${u}u.html; done

ui: ## Run the Streamlit UI locally
	API_URL=http://localhost:8000 $(BIN)/streamlit run ui/streamlit_app.py

k8s-up: ## kind cluster + NGINX Ingress + metrics-server + Helm release
	./scripts/kind/up.sh   # Windows: powershell -File scripts/kind/up.ps1

k8s-down: ## Delete the kind cluster
	./scripts/kind/down.sh

helm-lint: ## Lint and render the Helm chart
	helm lint helm/agentic-ai --set secrets.jwtSecret=x,secrets.adminPassword=x,secrets.postgresPassword=x
	helm template agentic-ai helm/agentic-ai -f helm/agentic-ai/values-aws.yaml > /dev/null

tf-plan: ## terraform fmt/validate/plan with mock AWS credentials ($0, nothing created)
	cd terraform && terraform fmt -check -recursive && terraform init -backend=false -input=false \
	  && terraform validate && terraform plan -var mock_aws=true -lock=false

clean: ## Remove caches and reports
	rm -rf .pytest_cache .ruff_cache reports **/__pycache__
