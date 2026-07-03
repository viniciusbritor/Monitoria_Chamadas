FROM python:3.11-slim

WORKDIR /app

# Dependências do sistema (faster-whisper precisa de compiladores?)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Instala todas as deps Python (incluindo firebase-admin, httpx, pyjwt)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código fonte (incluindo a pasta frontend/dist compilada pelo cloudbuild)
COPY . .

# Expõe a porta que o Cloud Run usa por padrão (8080)
EXPOSE 8080

# Força o encoding utf-8 para evitar problemas de Unicode no log (emoji do Whisper)
ENV PYTHONIOENCODING=utf-8

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]
