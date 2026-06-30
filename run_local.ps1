Write-Host "🚀 Iniciando Backend (FastAPI)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python -m uvicorn api:app --port 8001 --reload"

Write-Host "🚀 Iniciando Frontend (React/Vite)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd frontend; npm run dev -- --port 5174"

Write-Host "✅ Serviços do Ambiente de TESTE iniciados! Verifique as novas janelas do terminal." -ForegroundColor Green
Write-Host "🌐 O frontend estará disponível em: http://localhost:5174" -ForegroundColor Yellow
