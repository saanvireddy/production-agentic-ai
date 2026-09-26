# Build guide: from empty folder to portfolio project

The repository is complete, but the point is for you to own every piece of it. This guide walks the same order as the original plan and, for each stage, tells you which files implement it, how to run it, and what to check before moving on. Work through it on your own machine; the model-dependent numbers only become real there.

## Prerequisites

Docker Desktop (or Docker Engine), Python 3.11+, Ollama, and later kind, kubectl, Helm and Terraform. On a 16 GB laptop, `llama3.2:3b` is comfortable; with 32 GB try `llama3.1:8b` or `qwen2.5:7b`, which are noticeably better at SQL.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python --version && pip list | head -40
make test                       # 93 tests, no services needed
```

## Stage 1: the AI application (phases 4–11)

Files: `app/services/llm.py`, `app/rag/{embeddings,ingestion,vectorstore,pipeline}.py`, `app/database/{schema.sql,connection.py,seed.py}`, `app/main.py`.

```bash
ollama pull llama3.2:3b && ollama pull nomic-embed-text
docker compose up -d postgres redis
cp .env.example .env            # for running uvicorn on the host, uncomment the localhost URLs at the bottom
uvicorn app.main:app --reload   # applies schema, seeds, ingests PDFs
make eval-retrieval             # first real number: nomic retrieval quality
```

Check: `psql postgresql://agentic:<pw>@localhost:5432/agentic -c "select filename, num_pages, num_chunks from documents"` shows five documents, and a RAG question in Swagger returns `sources` with page numbers. Compare the retrieval report with the hash baseline in the README; nomic should fix the "daily meal allowance" miss.

Things worth understanding here: why chunks are split per page (citations), why the document title is prepended before embedding, what the `search_query:` / `search_document:` prefixes do for nomic, and why the HNSW index uses `vector_cosine_ops`.

## Stage 2: the agent (phases 12–17)

Files: `app/agents/{graph,router,prompts,validator}.py`, `app/sql/{guardrails,tool}.py`, `app/services/redis_store.py`.

Try the four canonical questions, then the follow-up and the destructive one:

```text
How many employees are in the Engineering department?
What about Finance?                       (same session_id)
Compare Engineering and Finance headcount.
Based on the company policies, what is the vacation policy for employees with more than 5 years of experience?
Delete all employees
```

```bash
make eval-sql                   # execution accuracy of your local model
pytest tests/test_guardrails.py -v
```

Check the `route_method` field: most questions should say `heuristic`. Try to break the SQL guardrail yourself (UNION into `users`, `pg_sleep`, a CTE with `DELETE`) and read how `validate_sql` walks the AST to stop it.

## Stage 3: production backend (phase 6 + 16)

Files: `app/auth/*`, `app/api/*`, `app/monitoring/logging.py`.

Get a token, call `/chat` without it (401), with an expired or tampered one (401), as a non-admin on `/documents` upload (403), and 31 times in a minute (429 with `Retry-After`). Stop Redis (`docker compose stop redis`) and confirm chat still answers, just without memory; that graceful degradation is deliberate.

## Stage 4: evaluation (phases 18–19)

```bash
make eval-ragas                 # needs the API running; creates .venv-eval on first run
cat reports/ragas_eval.md
```

The judge model matters a lot. A 3B judge is noisy; use `--judge-model llama3.1:8b` or larger if your machine allows. Record the numbers in the README results table together with the models used. If faithfulness is low, look at the per-question rows first: it is usually one or two answers that paraphrase a number.

## Stage 5: containers (phase 20)

```bash
docker compose up -d --build
docker compose ps               # everything healthy
docker compose exec api id      # uid=10001, not root
```

## Stage 6: Kubernetes (phases 21–24)

```bash
make k8s-up
kubectl -n agentic-ai get pods,svc,ingress,hpa
kubectl -n agentic-ai logs job/agentic-ai-bootstrap
```

To see the HPA work, generate CPU load with `make load-test` (first raise the limit with `--set config.RATE_LIMIT_PER_MINUTE=100000`, since all Locust users share one account) and watch `kubectl get hpa -w`. Note it takes about a minute for metrics-server to report and the scale-up policy adds two pods per minute.

Secrets: the chart refuses to render without `secrets.jwtSecret`, `adminPassword` and `postgresPassword`, which forces them to come from `--set` or a values file you never commit.

## Stage 7: observability (phases 25–28)

Open Grafana (Compose: http://localhost:3000) while running a load test. Then open Jaeger, pick service `agentic-api`, and look at a `/chat` trace: with a real model the `llm.*` spans are almost the whole request, which is the "where is the time going" answer you want for interviews. Stop Ollama to fire the `LLMErrors` alert in Prometheus (Alerts tab).

## Stage 8: CI/CD (phases 29–30)

Push the repository to GitHub. `tests`, `docker`, `evaluation` (retrieval gate) and `infra` run on the first push. Trigger the full LLM evaluation from the Actions tab (`evaluation` → Run workflow); it installs Ollama on the runner, so expect it to take a while on CPU. ECR push stays skipped until you set the `AWS_ROLE_ARN` repository variable.

## Stage 9: infrastructure as code (phases 31–32)

```bash
cd terraform && cp terraform.tfvars.example terraform.tfvars
terraform fmt -check -recursive && terraform init -backend=false && terraform validate
terraform plan -var mock_aws=true
```

Read the plan and match resources to the AWS diagram in `docs/architecture.md`. Things to be able to explain: why nodes run in private subnets, why IMDSv2 hop limit 1 matters with IRSA, why the GitHub role trust is pinned to `refs/heads/main`, and why secrets end up in Terraform state (and therefore why the S3 backend must be encrypted).

## Stage 10: polish (phases 35–40)

Take the screenshots listed at the end of the README, record a two-minute demo (the four canonical questions, the destructive one, then Grafana and a Jaeger trace), and only then write the resume and LinkedIn text, using your measured numbers.
