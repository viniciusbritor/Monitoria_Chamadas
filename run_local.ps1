Write-Host "🚀 Iniciando Backend (FastAPI)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "uvicorn api:app --reload"

Write-Host "🚀 Iniciando Frontend (React/Vite)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd frontend; npm run dev"

Write-Host "✅ Serviços iniciados! Verifique as novas janelas do terminal." -ForegroundColor Green
Write-Host "🌐 O frontend estará disponível em: http://localhost:5173" -ForegroundColor Yellow
