param(
    [ValidateSet("worker","test-env","both","auto")]
    [string]$Target = "auto"
)

$ErrorActionPreference = "Stop"
$sha = git log --format="%H" -1
$short = $sha.Substring(0,7)
$project = "coherence-ominichannel-fs"

Write-Host "=== Deploy Monitoria Chamadas ===" -ForegroundColor Cyan
Write-Host "Commit: $short" -ForegroundColor Gray

# Deteccao automatica: quais arquivos mudaram?
if ($Target -eq "auto") {
    $changed = git diff --name-only HEAD~1..HEAD
    Write-Host "Arquivos alterados:" -ForegroundColor Gray
    $changed | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }

    $hasWorkerChanges = $false
    $hasTestEnvChanges = $false

    foreach ($f in $changed) {
        if ($f -match '^worker\.py$|^Dockerfile\.worker$|^cloudbuild-worker\.yaml$|^requirements\.txt$|^core/') {
            $hasWorkerChanges = $true
        }
        if ($f -match '^api\.py$|^Dockerfile$|^cloudbuild-test\.yaml$|^frontend/') {
            $hasTestEnvChanges = $true
        }
    }

    if ($hasWorkerChanges -and $hasTestEnvChanges) { $Target = "both" }
    elseif ($hasWorkerChanges) { $Target = "worker" }
    elseif ($hasTestEnvChanges) { $Target = "test-env" }
    else { $Target = "none" }
}

switch ($Target) {
    "worker" {
        Write-Host "`nDeployando WORKER ($short)..." -ForegroundColor Yellow
        gcloud builds submit --config=cloudbuild-worker.yaml `
            --project=$project --substitutions=COMMIT_SHA=$sha . 2>&1
        Write-Host "Worker deployado!" -ForegroundColor Green
    }
    "test-env" {
        Write-Host "`nDeployando TEST-ENV ($short)..." -ForegroundColor Yellow
        gcloud builds submit --config=cloudbuild-test.yaml `
            --project=$project --substitutions=COMMIT_SHA=$sha . 2>&1
        Write-Host "Test-env deployado!" -ForegroundColor Green
    }
    "both" {
        Write-Host "`nDeployando WORKER + TEST-ENV em paralelo ($short)..." -ForegroundColor Yellow
        $j1 = Start-Job -ScriptBlock {
            param($p, $s) gcloud builds submit --config=cloudbuild-worker.yaml --project=$p --substitutions=COMMIT_SHA=$s .
        } -ArgumentList $project, $sha
        $j2 = Start-Job -ScriptBlock {
            param($p, $s) gcloud builds submit --config=cloudbuild-test.yaml --project=$p --substitutions=COMMIT_SHA=$s .
        } -ArgumentList $project, $sha
        $j1, $j2 | Receive-Job -Wait -AutoRemoveJob
        Write-Host "Worker + Test-env deployados!" -ForegroundColor Green
    }
    "none" {
        Write-Host "`nNenhum arquivo relevante mudou. Deploy ignorado." -ForegroundColor Gray
        Write-Host "Para deploy forçado:" -ForegroundColor Gray
        Write-Host "  .\scripts\deploy.ps1 -Target both" -ForegroundColor DarkGray
    }
}
