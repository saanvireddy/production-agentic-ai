#!/usr/bin/env bash
# Local Kubernetes deployment on kind:
#   cluster -> NGINX Ingress -> metrics-server (for HPA) -> images -> Helm release.
#
#   ./scripts/kind/up.sh                   # in-cluster Ollama (slow on CPU; ~6 GB RAM for Docker)
#   OLLAMA_URL=http://host.docker.internal:11434 ./scripts/kind/up.sh   # use Ollama on your host instead
set -euo pipefail
cd "$(dirname "$0")/../.."

CLUSTER=agentic-ai
NS=agentic-ai
: "${JWT_SECRET:=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')}"
: "${ADMIN_PASSWORD:=admin123}"
: "${POSTGRES_PASSWORD:=$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')}"

if ! kind get clusters | grep -qx "$CLUSTER"; then
  kind create cluster --config scripts/kind/kind-config.yaml
fi

echo ">> NGINX Ingress"
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.13.2/deploy/static/provider/kind/deploy.yaml
kubectl -n ingress-nginx rollout status deploy/ingress-nginx-controller --timeout=180s

echo ">> metrics-server (HPA needs CPU/memory metrics)"
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl -n kube-system patch deploy metrics-server --type=json \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]' || true

echo ">> Build and load images"
docker build -t production-agentic-ai:1.0.0 .
docker build -t production-agentic-ai-ui:1.0.0 -f docker/ui.Dockerfile .
kind load docker-image production-agentic-ai:1.0.0 production-agentic-ai-ui:1.0.0 --name "$CLUSTER"

echo ">> Helm release"
EXTRA=()
if [[ -n "${OLLAMA_URL:-}" ]]; then
  EXTRA+=(--set ollama.enabled=false --set externalUrls.ollamaUrl="$OLLAMA_URL")
fi
helm upgrade --install agentic-ai helm/agentic-ai -n "$NS" --create-namespace \
  --set secrets.jwtSecret="$JWT_SECRET" \
  --set secrets.adminPassword="$ADMIN_PASSWORD" \
  --set secrets.postgresPassword="$POSTGRES_PASSWORD" \
  ${EXTRA[@]+"${EXTRA[@]}"} --wait --timeout 15m

kubectl -n "$NS" get pods,svc,ingress,hpa
echo
echo "Add '127.0.0.1 agentic.local' to /etc/hosts, then open http://agentic.local (UI) and http://agentic.local/docs (API)."
