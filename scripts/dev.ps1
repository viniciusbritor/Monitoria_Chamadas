<#
.SYNOPSIS
  Gerencia ambiente de teste Monitoria sob demanda.
  Sobe/desliga servicos de teste para economizar custo.

.DESCRIPTION
  up   - Deploya ambiente de teste via Cloud Build + sobe worker
  down - Escala worker test para zero (custo $0/mes ate proximo dev)

.EXAMPLE
  .\scripts\dev.ps1 up
  .\scripts\dev.ps1 down
#>

param(
    [Parameter(Mandatory)]
    [ValidateSet("up", "down")]
    [string]$action
)

$PROJECT = "coherence-ominichannel-fs"
$REGION = "us-central1"
$WORKER = "monitoria-whisper-worker"
$API = "monitoria-test-env"

if ($action -eq "up") {
    Write-Host "=== Subindo ambiente de teste ===" -ForegroundColor Green

    # Trigger manual dos Cloud Builds
    Write-Host "[1/2] Deployando API test-env..." -ForegroundColor Cyan
    gcloud builds submit --config=cloudbuild-test.yaml --project=$PROJECT --substitutions=COMMIT_SHA=$(git rev-parse HEAD) .

    Write-Host "[2/2] Deployando Worker test..." -ForegroundColor Cyan
    gcloud builds submit --config=cloudbuild-worker.yaml --project=$PROJECT --substitutions=COMMIT_SHA=$(git rev-parse HEAD) .

    Write-Host ""
    Write-Host "=== Ambiente de teste pronto! ===" -ForegroundColor Green
    Write-Host "API: https://monitoria-test-env-c5nbfc5meq-uc.a.run.app" -ForegroundColor Cyan
    Write-Host "Para testar, obtenha o token do Portal e acesse a URL com ?token=..." -ForegroundColor Gray
    Write-Host "Worker: min-instances=1 (temporario apos deploy)" -ForegroundColor Cyan
}

if ($action -eq "down") {
    Write-Host "=== Desligando ambiente de teste ===" -ForegroundColor Yellow

    Write-Host "[1/1] Escalando worker para zero..." -ForegroundColor Cyan
    gcloud run services update $WORKER --region=$REGION --project=$PROJECT --min-instances=0 --quiet

    Write-Host ""
    Write-Host "=== Ambiente de teste desligado (custo R$ 0/mes) ===" -ForegroundColor Green
    Write-Host "Worker nao processara mensagens ate proximo deploy." -ForegroundColor Gray
    Write-Host "Para reativar: .\scripts\dev.ps1 up" -ForegroundColor Cyan
}
