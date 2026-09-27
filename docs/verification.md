# Verification log

What was actually executed while building this repository, and what could not be run in the build environment. The build sandbox had Python, a local PostgreSQL 16 with pgvector 0.6, Redis 7, Prometheus 3.5 and Jaeger 1.73, but no access to Docker Hub or the Ollama model registry, so no container images could be pulled and no real LLM could be run.

## Verified

| Area | Check | Result |
|---|---|---|
| Unit/API tests | `pytest` (auth, guardrails, RAG, SQL, agent, API, evaluation gates) | 93 passed |
| Integration | `pytest -m integration` against real Postgres/pgvector + Redis | 6 passed, including the READ ONLY transaction rejecting `DELETE` |
| Lint | `ruff check` + `ruff format --check` | clean |
| Runtime deps | `pip install -r requirements.txt` into a fresh venv, import app | OK |
| End-to-end API | uvicorn + real Postgres/Redis, fake LLM, hash embeddings: login, SQL, RAG with citations, follow-up memory, destructive-request block | OK |
| Retrieval eval | `python -m app.evaluation.retrieval` over pgvector (hash embeddings) | hit@4 0.938, MRR 0.938 |
| Load test | Locust 10/50/100 users, 45 s each, fake LLM | 0 failures; see README table |
| Prometheus | `promtool check config` + `check rules`; live scrape of the API | valid; 6 alert rules loaded |
| Grafana dashboard | every panel query executed against live Prometheus after load | 22/22 queries return data |
| OpenTelemetry | API exporting OTLP to Jaeger all-in-one | `agentic-api` service with full span tree |
| Streamlit UI | Playwright: login → SQL question → follow-up | 4 chat messages rendered, follow-up rewritten |
| Kubernetes | kubeconform `-strict` on `k8s/` (K8s 1.31 schemas) | 23/23 resources valid |
| Helm | chart rendered with a Go text/template + sprig renderer (local and AWS values), then kubeconform incl. ExternalSecret/ServiceMonitor CRD schemas | 35/35 resources valid |
| Docker Compose | `docker compose config` (default and `ollama` profile) | valid |
| GitHub Actions | actionlint on all four workflows | clean |
| Terraform | `tofu fmt -check -recursive`; HCL parse of every file; module input/output cross-reference check | clean |

The chart render check found and fixed a real bug (duplicate `app.kubernetes.io/instance` labels on the API Deployment and Service), and the live Prometheus check found another (metric path labels missing the `/api/v1` prefix because FastAPI 0.14x reports included routes without it). Both have regression coverage now.

## Not run here (run these on your machine or in CI)

| Check | Why not here | Where it runs |
|---|---|---|
| Real LLM answers, SQL execution accuracy, Ragas scores | no Ollama models | `make eval-sql`, `make eval-ragas`, `evaluation.yml` (llm-eval job) |
| nomic-embed-text retrieval numbers | no Ollama models | `make eval-retrieval` |
| `docker build` / `docker compose up` | Docker Hub blocked | locally; `docker.yml` builds, smoke-tests and scans both images |
| `helm lint` with the real helm binary | binary unavailable | `make helm-lint`; `infra.yml` |
| `terraform init/validate/plan` | provider registry unavailable | `make tf-plan`; `infra.yml` |
| A live Kubernetes cluster (HPA scaling, Ingress) | no cluster images | `make k8s-up` |


## Verified on a Windows laptop (Docker Desktop, native Ollama)

| Check | Result |
|---|---|
| `docker compose up` with Ollama (`llama3.2:3b`, `nomic-embed-text`) | all services healthy; UI answered SQL, follow-up, RAG and blocked the destructive request |
| Retrieval eval (nomic-embed-text) | hit@4 1.000, page recall 1.000, hit@1 0.938, MRR 0.958 |
| SQL execution accuracy (`llama3.2:3b`) | 70% (7/10) |
| Ragas (`llama3.1:8b` judge) | faithfulness 0.689, answer relevancy 0.743, context precision 0.724, context recall 0.700 |
| kind cluster + NGINX Ingress + metrics-server + Helm release | 2 API pods, HPA reading metrics, bootstrap Job completed, UI answered via http://agentic.local |
| `terraform fmt / init / validate / plan -var mock_aws=true` | valid; `Plan: 71 to add, 0 to change, 0 to destroy` |

Bugs found and fixed during this run: the `/openapi.json` ingress path needed `pathType: ImplementationSpecific` (ingress-nginx strict path validation), the kind ingress controller had to be pinned to the control-plane node that owns the host port mapping, and the data-tier security-group rules needed static `for_each` keys so `terraform plan` can run before the security groups exist.