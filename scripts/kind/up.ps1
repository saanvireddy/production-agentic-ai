<#
Local Kubernetes deployment on kind (Windows / PowerShell).
  cluster -> NGINX Ingress -> metrics-server (for HPA) -> build + load images -> Helm release

Usage (from the repo root):
  powershell -ExecutionPolicy Bypass -File scripts\kind\up.ps1                       # uses Ollama running on Windows
  powershell -ExecutionPolicy Bypass -File scripts\kind\up.ps1 -InClusterOllama      # runs Ollama inside the cluster
#>
param(
    [switch]$InClusterOllama,
    [string]$AdminPassword = "admin123",
    [string]$OllamaUrl = "http://host.docker.internal:11434"
)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")

function New-Secret([int]$bytes) {
    $b = New-Object byte[] $bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    return ([Convert]::ToBase64String($b) -replace '[+/=]', '')
}
function Run([string]$cmd) {
    Write-Host ">> $cmd" -ForegroundColor Cyan
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) { throw "command failed: $cmd" }
}

$Cluster = "agentic-ai"
$Ns = "agentic-ai"
$JwtSecret = New-Secret 48
$PgPassword = New-Secret 18

$existing = (kind get clusters) -split "`n"
if ($existing -notcontains $Cluster) {
    Run "kind create cluster --config scripts/kind/kind-config.yaml"
}

Write-Host "`n== NGINX Ingress (kind flavour)" -ForegroundColor Green
Run "kubectl apply -f https://kind.sigs.k8s.io/examples/ingress/deploy-ingress-nginx.yaml"
Run "kubectl -n ingress-nginx patch deployment ingress-nginx-controller --patch-file scripts/kind/ingress-controller-patch.yaml"
Run "kubectl -n ingress-nginx rollout status deployment ingress-nginx-controller --timeout=300s"

Write-Host "`n== metrics-server (HPA needs CPU/memory metrics)" -ForegroundColor Green
Run "kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml"
# kind's kubelets use self-signed certs; patch via a file to avoid PowerShell JSON-quoting differences.
kubectl -n kube-system patch deploy metrics-server --type=json --patch-file scripts/kind/metrics-server-patch.json

Write-Host "`n== Build and load images" -ForegroundColor Green
Run "docker build -t production-agentic-ai:1.0.0 ."
Run "docker build -t production-agentic-ai-ui:1.0.0 -f docker/ui.Dockerfile ."
Run "kind load docker-image production-agentic-ai:1.0.0 production-agentic-ai-ui:1.0.0 --name $Cluster"

Write-Host "`n== Helm release" -ForegroundColor Green
$helmArgs = @(
    "upgrade", "--install", "agentic-ai", "helm/agentic-ai", "-n", $Ns, "--create-namespace",
    "--set", "secrets.jwtSecret=$JwtSecret",
    "--set", "secrets.adminPassword=$AdminPassword",
    "--set", "secrets.postgresPassword=$PgPassword",
    "--wait", "--timeout", "15m"
)
if (-not $InClusterOllama) {
    $helmArgs += @("--set", "ollama.enabled=false", "--set", "externalUrls.ollamaUrl=$OllamaUrl")
}
& helm @helmArgs
if ($LASTEXITCODE -ne 0) { throw "helm install failed" }

kubectl -n $Ns get pods,svc,ingress,hpa
Write-Host "`nAdd '127.0.0.1 agentic.local' to C:\Windows\System32\drivers\etc\hosts (as Administrator)," -ForegroundColor Yellow
Write-Host "then open http://agentic.local (UI) and http://agentic.local/docs (API). Login: admin / $AdminPassword" -ForegroundColor Yellow